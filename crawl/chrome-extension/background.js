/*
 * Background service worker: chay o nen, khong phu thuoc popup mo/đong.
 *
 * Nhan START_CRAWL tu popup, dieu huong NGAY TAB DANG MO qua tung bai viet,
 * doi load xong, trich noi dung, luu vao chrome.storage.local.
 * Sau khi xong tat ca, quay ve URL group ban dau.
 */

const STORAGE_KEY = "fb_posts";
const CRAWL_STATE_KEY = "fb_crawl_state";
const LOAD_TIMEOUT_MS = 30000;
const RENDER_PAUSE_MS = 2500;

const crawlState = {
  running: false,
  paused: false,
  tabId: null,
  originalUrl: null,
  total: 0,
  done: 0,
  error: "",
};

/**
 * Cho tab load xong (status=complete) hoac het thoi gian timeout.
 *
 * Logic:
 *   - Lang nghe chrome.tabs.onUpdated de phat hien complete som nhat
 *   - Dang ky poll 500ms phong truong hop bo loi event (onUpdated miss)
 *   - Xong: cho them RENDER_PAUSE_MS de Facebook render noi dung
 *   - Het deadline van load -> tra ve ngay (khong treo crawl)
 *
 * @param {number} tabId - ID tab dang cho
 * @param {number} timeoutMs - Thoi gian toi da cho (ms)
 * @returns {Promise<void>}
 */
function waitForTabComplete(tabId, timeoutMs) {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    let timer = null;

    const cleanup = () => {
      chrome.tabs.onUpdated.removeListener(onUpdated);
      if (timer) clearTimeout(timer);
    };

    const finish = () => {
      cleanup();
      setTimeout(resolve, RENDER_PAUSE_MS);
    };

    const onUpdated = (updatedTabId, info) => {
      if (updatedTabId === tabId && info.status === "complete") finish();
    };

    const poll = () => {
      chrome.tabs.get(tabId, (tab) => {
        if (chrome.runtime.lastError || Date.now() > deadline) {
          cleanup();
          resolve();
          return;
        }
        if (tab.status === "complete") {
          finish();
          return;
        }
        timer = setTimeout(poll, 500);
      });
    };

    chrome.tabs.onUpdated.addListener(onUpdated);
    timer = setTimeout(() => {
      cleanup();
      resolve();
    }, timeoutMs);
    poll();
  });
}

/**
 * Bao dam content script da duoc inject vao tab.
 *
 * Logic:
 *   - Ping content script truoc; OK thi thoi
 *   - Loi (chua inject / tab vua load) -> inject lai content.js qua scripting
 *
 * @param {number} tabId - ID tab can kiem tra
 * @returns {Promise<void>}
 * @throws {Error} Neu inject that bai
 */
async function ensureContentScript(tabId) {
  try {
    const resp = await chrome.tabs.sendMessage(tabId, { type: "PING" });
    if (resp && resp.ok) return;
  } catch (_err) {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
    } catch (err) {
      throw new Error("inject content script that bai: " + err.message);
    }
  }
}

/**
 * Luu bai viet + trang thai crawl hien tai vao storage.
 *
 * Logic:
 *   - Luu STORAGE_KEY (bai viet) va CRAWL_STATE_KEY (trang thai) cung luc
 *   - Popup lang nghe storage.onChanged de cap nhat UI realtime
 *
 * @param {Array} posts - Danh sach bai viet (cap nhat mo lan crawl)
 * @param {string} [error] - Loi crawl (neu co), mac dinh giu nguyen
 * @returns {Promise<void>}
 */
async function persist(posts, error) {
  crawlState.error = error || "";
  await chrome.storage.local.set({
    [STORAGE_KEY]: posts,
    [CRAWL_STATE_KEY]: { ...crawlState },
  });
}

/**
 * Luu rieng trang thai crawl (khong cham toi bai viet).
 *
 * Logic:
 *   - Dung khi chi doi trang thai (pause/unpause, progress)
 *
 * @returns {Promise<void>}
 */
async function persistState() {
  await chrome.storage.local.set({ [CRAWL_STATE_KEY]: { ...crawlState } });
}

/**
 * Dung (block) luong crawl khi trang thai paused = true.
 *
 * Logic:
 *   - Poll storage moi 1s, thoat ngay khi paused = false
 *   - Dung truoc khi chuyen tab (o startCrawl) de khong mo bai khi paused
 *
 * @returns {Promise<void>}
 */
async function waitIfPaused() {
  while (true) {
    const { [CRAWL_STATE_KEY]: state } = await chrome.storage.local.get(CRAWL_STATE_KEY);
    if (!state || !state.paused) return;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

/**
 * Bat/tat trang thai paused cua crawl.
 *
 * Logic:
 *   - Cap nhat bien crawlState.paused roi luu qua persistState
 *   - Popup nut Tam dung/Tiep tuc goi SET_PAUSE -> ham nay
 *
 * @param {boolean} paused - True de tam dung, false de tiep tuc
 * @returns {Promise<void>}
 */
async function setPaused(paused) {
  crawlState.paused = paused;
  await persistState();
}

/**
 * Chay crawl: dieu huong tab qua tung bai, trich noi dung, luu lai.
 *
 * Logic:
 *   - Khoi tao trang thai (running, total, done=0) va luu ngay
 *   - Voi moi bai: cho neu paused -> chuyen tab toi bai -> cho load xong
 *     -> inject content script -> EXTRACT_CONTENT -> luu content/error
 *   - Sau moi bai persist de popup hien tien trinh thuc te
 *   - Loi 1 bai khong dung crawl (bat loi quanh tung bai)
 *   - Ket thuc: quay ve URL group ban dau, running = false
 *
 * @param {Array} posts - Danh sach bai viet (sua truc tiep: content, error)
 * @param {number} tabId - ID tab dung de crawl
 * @param {string|null} originalUrl - URL group de quay ve sau khi xong
 * @returns {Promise<void>}
 */
async function startCrawl(posts, tabId, originalUrl) {
  crawlState.running = true;
  crawlState.paused = false;
  crawlState.tabId = tabId;
  crawlState.originalUrl = originalUrl || null;
  crawlState.total = posts.length;
  crawlState.done = 0;
  crawlState.error = "";
  await chrome.storage.local.set({ [CRAWL_STATE_KEY]: { ...crawlState } });

  try {
    for (let i = 0; i < posts.length; i++) {
      const post = posts[i];
      await waitIfPaused();
      crawlState.done = i;
      await persist(posts);
      await chrome.tabs.update(tabId, { url: post.url });
      await waitForTabComplete(tabId, LOAD_TIMEOUT_MS);
      try {
        await ensureContentScript(tabId);
        const resp = await chrome.tabs.sendMessage(tabId, { type: "EXTRACT_CONTENT" });
        if (resp && resp.text && resp.text.trim()) {
          post.content = resp.text;
          post.error = "";
        } else {
          post.content = "";
          post.error = "trang rong - Facebook chan hoac bai khong hien thi";
        }
      } catch (err) {
        post.content = "";
        post.error = "khong trich duoc: " + err.message;
      }
      posts[i] = post;
      crawlState.done = i + 1;
      await persist(posts);
    }
  } catch (err) {
    await persist(posts, "loi xu ly: " + err.message);
  } finally {
    if (crawlState.originalUrl) {
      try {
        await chrome.tabs.update(crawlState.tabId, { url: crawlState.originalUrl });
      } catch (_err) {
        // tab co the da bi dong - bo qua
      }
    }
    crawlState.running = false;
    await persist(posts, crawlState.error);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "START_CRAWL") {
    startCrawl(message.posts, message.tabId, message.originalUrl).then(() => {
      sendResponse({ ok: true });
    });
    return true;
  }
  if (message && message.type === "SET_PAUSE") {
    setPaused(!!message.paused).then(() => {
      sendResponse({ ok: true });
    });
    return true;
  }
  if (message && message.type === "CRAWL_STATUS") {
    sendResponse({
      running: crawlState.running,
      paused: crawlState.paused,
      done: crawlState.done,
      total: crawlState.total,
      error: crawlState.error,
    });
  }
});
