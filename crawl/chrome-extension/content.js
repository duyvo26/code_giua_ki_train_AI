/*
 * Content script: chay trong trang group va trang bai viet Facebook.
 * Group ID duoc lay DONG TU URL tab dang mo (ho tro bat ky group nao).
 *
 * - COLLECT_POSTS: quet DOM trang group, tra ve 5 URL bai viet moi nhat.
 * - EXTRACT_CONTENT: quet DOM trang bai viet, tra ve noi dung (text) cua bai.
 *
 * Dang href co the gap trong feed group:
 *   - /groups/<id>/posts/<post_id>
 *   - /groups/<id>/permalink/<post_id>
 *   - story.php?story_fbid=<post_id>&id=<group_id>
 *   - /groups/<id>/?story_fbid=<post_id>
 */

function currentGroupId() {
  const fromPath = location.href.match(/groups\/(\d+)/);
  if (fromPath) return fromPath[1];
  const fromQuery = new URLSearchParams(location.search).get("id");
  return fromQuery || null;
}

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

function cleanText(text) {
  return (text || "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

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

function scanDiagnostics() {
  const rootCount = document.querySelectorAll('[id^="mount_0_"]').length;
  const articleCount = document.querySelectorAll('[role="article"]').length;
  const commentCount = document.querySelectorAll("[data-commentid]").length;
  const feedCount = document.querySelectorAll('[role="feed"]').length;
  return { rootCount, articleCount, commentCount, feedCount };
}

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

/* --- QUET THEO YEU CAU: chi chay khi bam nut "Quet ngay" ------------------- */

const STORAGE_KEY = "fb_posts";
const POST_COUNT_KEY = "fb_post_count";
let postLimit = 5;
let lastSavedSignature = "";

function applyPostCount() {
  chrome.storage.local.get(POST_COUNT_KEY).then((data) => {
    const value = parseInt(data[POST_COUNT_KEY], 10);
    if (value && value > 0) postLimit = value;
  });
}

function saveIfNew(posts) {
  if (!posts || posts.length === 0) return;
  const signature = posts.map((p) => p.url).join("|");
  if (signature === lastSavedSignature) return;
  lastSavedSignature = signature;
  const mapped = posts.map((p) => ({
    url: p.url,
    postText: p.postText,
    comments: p.comments,
    content: [
      p.postText,
      "",
      "--- BINH LUAN CONG KHAI (" + p.comments.length + ") ---",
      ...p.comments,
    ].join("\n"),
    error: "",
    commentCount: p.comments.length,
  }));
  chrome.storage.local.set({ [STORAGE_KEY]: mapped, fb_auto_done: true });
}

function scanNow() {
  if (!location.href.includes("/groups/")) return { posts: [], groupId: null };
  const result = collectPostsWithComments(postLimit);
  saveIfNew(result.posts);
  return result;
}
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[POST_COUNT_KEY]) {
    applyPostCount();
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "PING") {
    sendResponse({ ok: true });
  } else if (message && message.type === "SCAN_NOW") {
    const result = scanNow();
    const totalComments = result.posts.reduce((sum, p) => sum + p.comments.length, 0);
    sendResponse({
      count: result.posts.length,
      totalComments,
      groupId: result.groupId,
      debug: result.debug || null,
    });
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
