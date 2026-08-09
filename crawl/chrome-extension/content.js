/*
 * Content script: chay trong trang group va trang bai viet Facebook.
 * Group ID duoc lay DONG TU URL tab dang mo (ho tro bat ky group nao).
 *
 * - AUTO_SCAN: tu cuon trang thu thap bai + binh luan, LUU CONG DON
 *   (gop voi bai cu, loc trung theo url) - goi tu popup khi bam "Quet ngay".
 * - SCAN_NOW: quet 1 lan du lieu dang hien thi (van luu cong don).
 * - COLLECT_POSTS: quet DOM trang group, tra ve 5 URL bai viet moi nhat.
 * - EXTRACT_CONTENT: quet DOM trang bai viet, tra ve noi dung (text) cua bai.
 *
 * Dang href co the gap trong feed group:
 *   - /groups/<id>/posts/<post_id>
 *   - /groups/<id>/permalink/<post_id>
 *   - story.php?story_fbid=<post_id>&id=<group_id>
 *   - /groups/<id>/?story_fbid=<post_id>
 */

/**
 * Lay group id dang xem tu URL tab hien tai.
 *
 * Logic:
 *   - Uu tien group id trong duong dan /groups/<id>
 *   - Fallback query ?id= (dang story.php?story_fbid=..&id=..)
 *
 * @returns {string|null} Group id hoac null neu khong o trang group
 */
function currentGroupId() {
  const fromPath = location.href.match(/groups\/(\d+)/);
  if (fromPath) return fromPath[1];
  const fromQuery = new URLSearchParams(location.search).get("id");
  return fromQuery || null;
}

/**
 * Quet DOM trang group, tra ve toi da 5 URL bai viet moi nhat.
 *
 * Logic:
 *   - Duyet toan bo the <a>, khop regex 2 dang link:
 *     /groups/<id>/(posts|permalink)/<post_id> hoac story_fbid=<post_id>
 *   - Chuan hoa ve dang /groups/<id>/posts/<post_id>, loai trung qua Set
 *
 * @returns {string[]} Danh sach toi da 5 URL bai viet
 */
function collectPostUrls() {
  const groupId = currentGroupId();
  if (!groupId) return [];
  const postUrlRe = new RegExp(
    "(?:/groups/" + groupId + "/(?:posts|permalink)/(\\d+))|(?:story_fbid=(\\d+))"
  );
  const fullPostUrl = "https://www.facebook.com/groups/" + groupId + "/posts/{post_id}";
  const hrefs = Array.from(document.querySelectorAll("a[href]")).map((a) => a.href);
  const seen = new Set();
  const urls = [];
  for (const href of hrefs) {
    const match = href.match(postUrlRe);
    if (!match) continue;
    const postId = match[1] || match[2];
    const url = fullPostUrl.replace("{post_id}", postId);
    if (!seen.has(url)) {
      seen.add(url);
      urls.push(url);
    }
  }
  return urls.slice(0, 5);
}

/**
 * Trich noi dung bai viet dang mo (EXTRACT_CONTENT).
 *
 * Logic:
 *   - Uu tien [role="article"]: lay block message (data-ad-preview) hoac
 *     div[dir="auto"] dau tien, fallback toan bo innerText cua article
 *   - Khong co article -> lay innerText cua toan trang
 *   - Don xuong dong trung, gioi han 8000 ky tu
 *
 * @returns {{url: string, text: string}} URL hien tai + noi dung bai
 */
function extractPostContent() {
  const article = document.querySelector('[role="article"]');
  let text = "";
  if (article) {
    const messageBlock = article.querySelector('[data-ad-preview="message"], div[dir="auto"]');
    text = (messageBlock || article).innerText || "";
  } else {
    text = document.body.innerText || "";
  }
  text = text.replace(/\n{3,}/g, "\n\n").trim();
  return { url: location.href, text: text.slice(0, 8000) };
}

/**
 * Lam sach text tu DOM: bo khoang trang duoi cuoi dong, don xuong dong trung.
 *
 * Logic:
 *   - Khoang trang/tab truoc \n -> bo (xuong dong that)
 *   - 3+ xuong dong lien tiep -> gop thanh 2 (de doc)
 *   - Trim dau cuoi
 *
 * @param {string} text - Text tho tu innerText
 * @returns {string} Text da lam sach
 */
function cleanText(text) {
  return (text || "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

/**
 * Tim cac container bai viet trong DOM theo 3 muc do (co fallback).
 *
 * Logic:
 *   1) Feed semantic [role="feed"]: moi child co link bai viet la 1 bai
 *   2) Path cu the FB 2026: mount_0_* -> chuoi child khop vi tri da biet
 *      (DOM FB thay doi 2026 nen can path thu cong nay)
 *   3) Fallback: bat ky [role="article"] khong nam trong block binh luan
 *      (comment co data-commentid)
 *
 * @returns {{containers: Element[], mountFound: boolean}} Container bai viet
 *   + da tim thay mount path FB 2026 hay chua (de diagnostic)
 */
function findPostContainers() {
  const containers = [];
  let mountFound = false;

  // 1) Feed sematic: moi child cua [role="feed"] la 1 bai viet
  const feed = document.querySelector('[role="feed"]');
  if (feed) {
    for (const child of feed.children) {
      if (child.querySelector('a[href*="/posts/"], a[href*="story_fbid"], a[href*="permalink"]')) {
        containers.push(child);
      }
    }
    if (containers.length > 0) return { containers, mountFound: true };
  }

  // 2) Path cu the (FB 2026): mount_0_* > div > div[1] > div > div[3] > ... > div[2] > div
  const roots = document.querySelectorAll('[id^="mount_0_"]');
  for (const root of roots) {
    const base = root.querySelector(
      "div > div:nth-child(1) > div > div:nth-child(3) > div > div > " +
        "div:nth-child(1) > div:nth-child(1) > div:nth-child(4) > div > div > div > " +
        "div:nth-child(2) > div > div > div:nth-child(1) > div:nth-child(2) > div"
    );
    if (base) {
      mountFound = true;
      for (const child of base.children) {
        if (child.querySelector('a[href*="/posts/"], a[href*="story_fbid"], a[href*="permalink"]')) {
          containers.push(child);
        }
      }
    }
  }
  if (containers.length > 0) return { containers, mountFound };

  // 3) Fallback cuoi: bat ky [role="article"] khong nam trong comment
  const articles = Array.from(document.querySelectorAll('[role="article"]')).filter(
    (a) => !a.closest("[data-commentid]")
  );
  return { containers: articles, mountFound };
}

/**
 * Dem so luong cac thanh phan DOM chinh - dung de debug khi FB doi DOM.
 *
 * Logic:
 *   - Dem mount_0_* root, [role="article"], [data-commentid], [role="feed"]
 *   - Ket qua hien tren popup khi quet khong ra bai (SCAN_DEBUG)
 *
 * @returns {{rootCount: number, articleCount: number, commentCount: number, feedCount: number}} So lieu diagnostic
 */
function scanDiagnostics() {
  const rootCount = document.querySelectorAll('[id^="mount_0_"]').length;
  const articleCount = document.querySelectorAll('[role="article"]').length;
  const commentCount = document.querySelectorAll("[data-commentid]").length;
  const feedCount = document.querySelectorAll('[role="feed"]').length;
  return { rootCount, articleCount, commentCount, feedCount };
}

/**
 * Trich binh luan cong khai tu 1 container bai viet.
 *
 * Logic:
 *   - Moi block [data-commentid] la 1 binh luan
 *   - Lay ten tac gia tu a[href*="/user/"] span[dir="auto"] neu co
 *   - Noi dung: div[dir="auto"] dai nhat trong block
 *   - Loai truong hop "thoi gian" (vd "2 giờ trước") khong phai noi dung,
 *     kiem tra bang regex khoang thoi gian tieng Viet
 *
 * @param {Element} container - Container cua 1 bai viet
 * @returns {string[]} Danh sach binh luan ("ten: noi dung" neu co ten)
 */
function extractCommentsFromPost(container) {
  const comments = [];
  for (const commentEl of container.querySelectorAll("[data-commentid]")) {
    const authorEl = commentEl.querySelector('a[href*="/user/"] span[dir="auto"]');
    const messageEls = commentEl.querySelectorAll('div[dir="auto"]');
    let best = "";
    for (const el of messageEls) {
      const text = cleanText(el.innerText);
      if (text.length > best.length) best = text;
    }
    if (!best || /^(\d+ (giờ|phút|ngày|tuần|tháng|năm)|vừa xong)$/.test(best)) continue;
    const author = authorEl ? cleanText(authorEl.innerText) : "";
    comments.push(author ? author + ": " + best : best);
  }
  return comments;
}

/**
 * Trich noi dung bai viet (khong kem binh luan) tu container.
 *
 * Logic:
 *   - Lay toan bo div[dir="auto"] KHONG nam trong block binh luan
 *   - Noi dung bai = block text dai nhat (tranh lay tieu de/button)
 *
 * @param {Element} container - Container cua 1 bai viet
 * @returns {string} Noi dung bai viet da lam sach
 */
function extractPostText(container) {
  const candidates = Array.from(container.querySelectorAll('div[dir="auto"]')).filter(
    (el) => !el.closest("[data-commentid]")
  );
  let best = "";
  for (const el of candidates) {
    const text = cleanText(el.innerText);
    if (text.length > best.length) best = text;
  }
  return best;
}

/**
 * Trich 1 bai viet day du (id, url, text, comments) tu container.
 *
 * Logic:
 *   - Tim post_id tu link /groups/<id>/(posts|permalink)/<id> truoc,
 *     fallback story_fbid=<id>; da gap (seen) thi bo qua
 *   - Bai KHONG co binh luan cong khai -> tra null (bo qua)
 *
 * @param {Element} el - Container bai viet
 * @param {string} groupId - Group id dang xem
 * @param {Set<string>} seen - Set post_id da xu ly (loai trung)
 * @returns {{postId: string, url: string, postText: string, comments: string[]}|null} Bai viet hoac null
 */
function extractPostFromContainer(el, groupId, seen) {
  const hrefs = Array.from(el.querySelectorAll("a[href]")).map((a) => a.href);
  let postId = null;
  const postRe = new RegExp("/groups/" + groupId + "/(?:posts|permalink)/(\\d+)");
  for (const href of hrefs) {
    const m = href.match(postRe);
    if (m) {
      postId = m[1];
      break;
    }
  }
  if (!postId) {
    for (const href of hrefs) {
      const m = href.match(/story_fbid=(\d+)/);
      if (m) {
        postId = m[1];
        break;
      }
    }
  }
  if (!postId || seen.has(postId)) return null;

  const postText = extractPostText(el);
  const comments = extractCommentsFromPost(el);
  if (comments.length === 0) return null;

  return {
    postId,
    url: "https://www.facebook.com/groups/" + groupId + "/posts/" + postId,
    postText,
    comments,
  };
}

/**
 * Thu thap bai viet co binh luan cong khai tu trang group.
 *
 * Logic:
 *   - Tim container bai viet, moi container trich 1 bai (bo trung theo id)
 *   - Dung som khi du limit (mac dinh 5)
 *   - Kem ket qua scanDiagnostics + so container de popup debug
 *
 * @param {number} limit - So bai toi da can lay (0/null -> mac dinh 5)
 * @returns {{posts: Array, groupId: string|null, debug: Object}} Bai viet + thong tin debug
 */
function collectPostsWithComments(limit) {
  const groupId = currentGroupId();
  if (!groupId) return { posts: [], groupId: null, debug: scanDiagnostics() };
  const limitPosts = limit && limit > 0 ? limit : 5;
  const seen = new Set();
  const posts = [];
  const found = findPostContainers();
  const containers = found.containers;
  for (const el of containers) {
    const post = extractPostFromContainer(el, groupId, seen);
    if (!post) continue;
    seen.add(post.postId);
    posts.push({ url: post.url, postText: post.postText, comments: post.comments });
    if (posts.length >= limitPosts) break;
  }
  return { posts, groupId, debug: { ...scanDiagnostics(), containers: containers.length, mountFound: found.mountFound } };
}

/* --- QUET THEO YEU CAU: chay khi bam nut "Quet ngay" ---------------------- */

const STORAGE_KEY = "fb_posts";
const POST_COUNT_KEY = "fb_post_count";
const LOAD_WAIT_KEY = "fb_load_wait";

// Auto-scroll: cuon tung buoc, cho lazy-load roi thu thap cong don
const SCROLL_STEP_PX = 1200;
const DEFAULT_LOAD_WAIT_MS = 3000; // thoi gian cho load moi lan cuon
const MAX_SCROLLS = 30;            // gioi han an toan so lan cuon
const EMPTY_SCROLL_STOP = 4;       // 4 buoc khong co bai moi = het feed
const MAX_STORED_POSTS = 100;      // gioi han bai luu tru trong storage

let postLimit = 5;
let loadWaitMs = DEFAULT_LOAD_WAIT_MS;
let lastSavedSignature = "";

/**
 * Doc so bai toi da tu chrome.storage.local va cap nhat bien postLimit.
 *
 * Logic:
 *   - Doc POST_COUNT_KEY (mac dinh 5), parse int
 *   - Chi ap dung khi gia tri hop le (> 0)
 */
function applyPostCount() {
  chrome.storage.local.get(POST_COUNT_KEY).then((data) => {
    const value = parseInt(data[POST_COUNT_KEY], 10);
    if (value && value > 0) postLimit = value;
  });
}

/**
 * Doc thoi gian cho load tu chrome.storage.local va cap nhat bien loadWaitMs.
 *
 * Logic:
 *   - Doc LOAD_WAIT_KEY (mac dinh DEFAULT_LOAD_WAIT_MS), parse int
 *   - Kep trong khoang 500..10000ms de tranh gia tri vo ly
 */
function applyLoadWait() {
  chrome.storage.local.get(LOAD_WAIT_KEY).then((data) => {
    const value = parseInt(data[LOAD_WAIT_KEY], 10);
    if (value && value >= 500 && value <= 10000) loadWaitMs = value;
  });
}

/**
 * Chuan hoa 1 bai ve cau truc luu tru chuan (content gop text + binh luan).
 *
 * Logic:
 *   - content = postText + dau phan cach + danh sach binh luan
 *   - commentCount de popup thong ke nhanh khong can dem lai
 *
 * @param {Object} p - Bai viet tho (url, postText, comments)
 * @returns {Object} Bai viet da chuan hoa de luu storage
 */
function toStoredPost(p) {
  const comments = Array.isArray(p.comments) ? p.comments : [];
  return {
    url: p.url,
    postText: p.postText,
    comments,
    content: [
      p.postText,
      "",
      "--- BINH LUAN CONG KHAI (" + comments.length + ") ---",
      ...comments,
    ].join("\n"),
    error: p.error || "",
    commentCount: comments.length,
  };
}

/**
 * Luu bai viet CONG DON vao storage: gop voi bai cu + loc trung theo url.
 *
 * Logic:
 *   - Doc danh sach cu tu storage, map theo url (giu bai xuat hien truoc)
 *   - Bai moi chi them neu url chua co -> bai cu KHONG bi mat
 *   - Signature = danh sach url noi "|"; bang signature cu -> bo qua ghi
 *   - Gioi han MAX_STORED_POSTS de storage khong phinh ra
 *
 * @param {Array} posts - Danh sach bai moi (tu collectPostsWithComments)
 * @returns {Promise<{stored: Array, added: number}>} Bai da luu + so bai moi them
 */
async function saveMerged(posts) {
  if (!posts || posts.length === 0) return { stored: [], added: 0 };
  const { [STORAGE_KEY]: existing = [] } = await chrome.storage.local.get(STORAGE_KEY);

  const byUrl = new Map();
  for (const p of existing) {
    if (p && p.url && !byUrl.has(p.url)) byUrl.set(p.url, p);
  }
  let added = 0;
  for (const p of posts) {
    if (!p || byUrl.has(p.url)) continue;
    byUrl.set(p.url, p);
    added++;
  }

  const merged = Array.from(byUrl.values()).slice(0, MAX_STORED_POSTS);
  const signature = merged.map((p) => p.url).join("|");
  if (signature === lastSavedSignature) return { stored: merged, added: 0 };
  lastSavedSignature = signature;

  const mapped = merged.map(toStoredPost);
  await chrome.storage.local.set({ [STORAGE_KEY]: mapped, fb_auto_done: true });
  return { stored: mapped, added };
}

/**
 * Auto-scroll: tu cuon trang tung buoc, moi buoc thu thap bai moi
 * va luu CONG DON (loc trung), toi khi du limit hoac het feed.
 *
 * Logic:
 *   - Buoc 1: quet DOM hien tai truoc (chua cuon), luu, bao tien trinh
 *   - Moi vong: du limit -> dung ("enough"); qua EMPTY_SCROLL_STOP buoc
 *     lien tiep khong co bai moi -> het feed ("end_of_feed")
 *   - Cuon xuong SCROLL_STEP_PX roi cho loadWaitMs cho lazy-load
 *   - Cham MAX_SCROLLS -> dung an toan ("max_scrolls")
 *   - Sau moi lan luu goi onProgress de popup cap nhat realtime
 *
 * @param {number} limit - So bai toi da can thu thap
 * @param {Function} [onProgress] - Callback ({count, totalComments, scrolls})
 * @returns {Promise<{posts: Array, groupId: string|null, stopped: string, scrolls: number}>}
 */
async function autoScrollScan(limit, onProgress) {
  const groupId = currentGroupId();
  if (!groupId || !location.href.includes("/groups/")) {
    return { posts: [], groupId: null, stopped: "no_group", scrolls: 0 };
  }
  const limitPosts = limit && limit > 0 ? limit : postLimit;
  const allPosts = [];
  const seenUrls = new Set();
  let scrolls = 0;
  let emptyScrolls = 0;

  const emitProgress = () => {
    const totalComments = allPosts.reduce((sum, p) => sum + p.comments.length, 0);
    if (onProgress) onProgress({ count: allPosts.length, totalComments, scrolls });
  };

  while (scrolls < MAX_SCROLLS) {
    // Quet bai hien tai (lan dau la feed dau trang, sau moi lan cuon la doan moi)
    const result = collectPostsWithComments(limitPosts);
    let freshCount = 0;
    for (const p of result.posts) {
      if (seenUrls.has(p.url)) continue;
      seenUrls.add(p.url);
      allPosts.push(p);
      freshCount++;
    }
    emptyScrolls = freshCount > 0 ? 0 : emptyScrolls + 1;

    await saveMerged(allPosts);
    emitProgress();

    if (allPosts.length >= limitPosts) {
      return { posts: allPosts, groupId, stopped: "enough", scrolls: scrolls + 1, debug: result.debug };
    }
    if (emptyScrolls >= EMPTY_SCROLL_STOP) {
      return { posts: allPosts, groupId, stopped: "end_of_feed", scrolls: scrolls + 1, debug: result.debug };
    }

    window.scrollBy(0, SCROLL_STEP_PX);
    await new Promise((resolve) => setTimeout(resolve, loadWaitMs));
    scrolls++;
  }
  return { posts: allPosts, groupId, stopped: "max_scrolls", scrolls, debug: null };
}

/**
 * Quet ngay lap tuc tren trang group hien tai (SCAN_NOW) - luu cong don.
 *
 * Logic:
 *   - Chi chay khi dang o trang /groups/ (khong phai trang khac)
 *   - Thu thap bai voi postLimit da cau hinh roi luu qua saveMerged
 *
 * @returns {Promise<{posts: Array, groupId: string|null}>} Ket qua quet hien tai
 */
async function scanNow() {
  if (!location.href.includes("/groups/")) return { posts: [], groupId: null };
  const result = collectPostsWithComments(postLimit);
  await saveMerged(result.posts);
  return result;
}
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local") {
    if (changes[POST_COUNT_KEY]) applyPostCount();
    if (changes[LOAD_WAIT_KEY]) applyLoadWait();
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "PING") {
    sendResponse({ ok: true });
  } else if (message && message.type === "AUTO_SCAN") {
    // Auto-scroll async: tra loi sau khi xong, bao tien trinh moi buoc
    autoScrollScan(message.limit || postLimit, (prog) => {
      // Popup co the dong giua chung - ket qua van duoc luu vao storage
      chrome.runtime.sendMessage({ type: "FB_SCAN_PROGRESS", ...prog }).catch(() => {});
    }).then((result) => {
      const totalComments = result.posts.reduce((sum, p) => sum + p.comments.length, 0);
      sendResponse({ ...result, count: result.posts.length, totalComments });
    });
    return true;
  } else if (message && message.type === "SCAN_NOW") {
    scanNow().then((result) => {
      const totalComments = result.posts.reduce((sum, p) => sum + p.comments.length, 0);
      sendResponse({
        count: result.posts.length,
        totalComments,
        groupId: result.groupId,
        debug: result.debug || null,
      });
    });
    return true;
  } else if (message && message.type === "SCAN_DEBUG") {
    sendResponse({ ...scanDiagnostics(), groupId: currentGroupId(), url: location.href });
  } else if (message && message.type === "COLLECT_POSTS") {
    sendResponse({ urls: collectPostUrls(), groupId: currentGroupId() });
  } else if (message && message.type === "COLLECT_POSTS_WITH_COMMENTS") {
    sendResponse(collectPostsWithComments());
  } else if (message && message.type === "EXTRACT_CONTENT") {
    sendResponse(extractPostContent());
  }
});
