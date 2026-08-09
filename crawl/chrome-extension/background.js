/*
 * Background service worker: chay o nen, khong phu thuoc popup mo/đong.
 *
 * - START_CRAWL: dieu huong tab qua tung bai viet, trich noi dung (cu).
 * - START_AUTO_CRAWL: AUTO mo tung trang group da cau hinh (tab moi nen):
 *     doi load + delay -> check dung URL -> content tu scroll lay bai
 *     -> gui ve web /api/extension/analyze ngay sau moi trang
 *     -> xong (hoac bam Dung) -> tu dong dong tab.
 * - STOP_AUTO_CRAWL: dung sau trang hien tai.
 */

const STORAGE_KEY = "fb_posts";
const CRAWL_STATE_KEY = "fb_crawl_state";
const WEB_URL_KEY = "fb_web_url";
const API_KEY_KEY = "fb_api_key";
const LOAD_TIMEOUT_MS = 30000;
const RENDER_PAUSE_MS = 2500;
// Phai khop EXT_VERSION trong content.js - cu hon thi re-inject lai
const EXPECTED_EXT_VERSION = 6;

const crawlState = {
  running: false,
  paused: false,
  tabId: null,
  originalUrl: null,
  total: 0,
  done: 0,
  error: "",
};

// Trang thai auto-crawl (mo nhieu trang group)
const autoJob = {
  running: false,
  stop: false,
  urls: [],
  total: 0,
  done: 0,
  tabId: null,
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
 * Bao dam content script ban MOI da duoc inject vao tab.
 *
 * Logic:
 *   - Ping content script; phai tra ve dung version (EXPECTED_EXT_VERSION)
 *   - Khong co phan hoi (chua inject) HOAC version cu (script cu con song
 *     sau khi reload extension ma chua F5) -> inject lai content.js
 *
 * @param {number} tabId - ID tab can kiem tra
 * @returns {Promise<void>}
 * @throws {Error} Neu inject that bai
 */
async function ensureContentScript(tabId) {
  let resp = null;
  try {
    resp = await chrome.tabs.sendMessage(tabId, { type: "PING" });
  } catch (_err) {
    resp = null;
  }
  if (resp && resp.ok && resp.version === EXPECTED_EXT_VERSION) return;
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
  } catch (err) {
    throw new Error("inject content script that bai: " + err.message);
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

/**
 * Gui bai viet cua 1 trang ve web /api/extension/analyze (X-API-Key).
 *
 * Logic:
 *   - Doc webUrl + apiKey truc tiep tu chrome.storage (background co quyen)
 *   - Chua cau hinh -> tra loi ro de popup biet
 *   - Loi HTTP -> giu message tu server (vd 401 key sai) de hien thi
 *
 * @param {Array} posts - Danh sach bai cua trang vua quet
 * @returns {Promise<{ok: boolean, message: string}>} Ket qua gui
 */
async function sendPageToWeb(posts) {
  const { [WEB_URL_KEY]: webUrl, [API_KEY_KEY]: apiKey } = await chrome.storage.local.get([
    WEB_URL_KEY,
    API_KEY_KEY,
  ]);
  if (!webUrl || !apiKey) {
    return { ok: false, message: "chua cau hinh URL web / API key trong extension" };
  }
  try {
    const resp = await fetch(webUrl.replace(/\/+$/, "") + "/api/extension/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({ posts }),
    });
    const data = await resp.json().catch(() => ({}));
    return { ok: resp.ok, message: data.message || data.error || ("HTTP " + resp.status) };
  } catch (err) {
    return { ok: false, message: "loi gui web: " + err.message };
  }
}

/**
 * Chay AUTO-CRAWL: mo TUNG trang group da cau hinh (tab moi nen), doi load
 * + delay, check dung URL, content tu scroll lay bai, gui web ngay sau moi trang.
 *
 * Logic:
 *   - Tao tab moi nen (active=false) de khong lam on tab dang dung cua nguoi dung
 *   - Voi moi URL: tabs.update -> waitForTabComplete -> cho delayMs (5s)
 *     -> ensureContentScript (version check) -> AUTO_SCAN {limit, expectedUrl}
 *   - Content tra skipped (URL sai/login wall) -> bo qua, ghi ly do
 *   - Co bai moi -> sendPageToWeb() NGAY (web tu phan tich + tu gui bot)
 *   - Sau moi trang broadcast AUTO_CRAWL_PROGRESS cho popup
 *   - Kiem tra autoJob.stop truoc moi trang (nut Dung) - trang dang chay
 *     cho chay het roi moi dung
 *   - Xong: neu closeTab -> chrome.tabs.remove(tabId); luon broadcast
 *     AUTO_CRAWL_DONE {stopped, done, total}
 *   - Loi tao tab -> fallback dung tab active hien tai va KHONG dong
 *
 * @param {string[]} urls - Danh sach URL group (1 URL/dong tu popup)
 * @param {number} delayMs - Thoi gian cho sau khi trang load xong truoc khi quet
 * @param {number} limit - So bai toi da quet moi trang
 * @param {boolean} closeTab - Tu dong dong tab sau khi xong
 * @returns {Promise<void>}
 */
async function startAutoCrawl(urls, delayMs, limit, closeTab) {
  autoJob.running = true;
  autoJob.stop = false;
  autoJob.urls = urls;
  autoJob.total = urls.length;
  autoJob.done = 0;

  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const activeTab = tabs && tabs.length > 0 ? tabs[0] : null;
  let tabId = null;
  let ownTab = false;
  if (activeTab) {
    try {
      const created = await chrome.tabs.create({ url: urls[0], active: false });
      tabId = created.id;
      ownTab = true;
    } catch (_err) {
      tabId = activeTab.id; // fallback: dung tab hien tai, khong dong
    }
  }

  try {
    for (let i = 0; i < urls.length; i++) {
      if (autoJob.stop) break;
      if (tabId === null) break;
      const url = urls[i];
      let pageCount = 0;
      let totalComments = 0;
      let skipReason = "";
      let sent = null;

      try {
        await chrome.tabs.update(tabId, { url });
        await waitForTabComplete(tabId, LOAD_TIMEOUT_MS);
        // Delay theo cau hinh (mac dinh 5s) cho Facebook render xong feed
        await new Promise((resolve) => setTimeout(resolve, delayMs));

        await ensureContentScript(tabId);
        const resp = await chrome.tabs.sendMessage(tabId, {
          type: "AUTO_SCAN",
          limit,
          expectedUrl: url,
        });
        if (resp && resp.skipped) {
          skipReason = resp.reason || "skip";
        } else if (resp && Array.isArray(resp.posts)) {
          pageCount = resp.posts.length;
          totalComments = resp.totalComments || 0;
          if (pageCount > 0) {
            sent = await sendPageToWeb(resp.posts);
          }
        }
      } catch (err) {
        skipReason = "loi: " + err.message;
      }

      autoJob.done = i + 1;
      chrome.runtime.sendMessage({
        type: "AUTO_CRAWL_PROGRESS",
        done: autoJob.done,
        total: autoJob.total,
        url,
        pageCount,
        totalComments,
        skipReason,
        sent,
      }).catch(() => {});
    }
  } finally {
    if (ownTab && closeTab && tabId !== null) {
      try {
        await chrome.tabs.remove(tabId);
      } catch (_err) {
        // tab co the da bi dong - bo qua
      }
    }
    autoJob.running = false;
    chrome.runtime.sendMessage({
      type: "AUTO_CRAWL_DONE",
      stopped: autoJob.stop,
      done: autoJob.done,
      total: autoJob.total,
      tabClosed: ownTab && closeTab,
    }).catch(() => {});
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "START_CRAWL") {
    startCrawl(message.posts, message.tabId, message.originalUrl).then(() => {
      sendResponse({ ok: true });
    });
    return true;
  }
  if (message && message.type === "START_AUTO_CRAWL") {
    if (autoJob.running) {
      sendResponse({ ok: false, error: "Auto-crawl dang chay roi" });
      return;
    }
    const urls = Array.isArray(message.urls)
      ? message.urls.map((u) => String(u).trim()).filter(Boolean)
      : [];
    if (urls.length === 0) {
      sendResponse({ ok: false, error: "Chua co trang nao de auto-crawl" });
      return;
    }
    startAutoCrawl(
      urls,
      Math.max(1000, parseInt(message.delayMs, 10) || 5000),
      Math.max(1, parseInt(message.limit, 10) || 5),
      message.closeTab !== false
    ).then(() => {
      sendResponse({ ok: true });
    });
    return true;
  }
  if (message && message.type === "STOP_AUTO_CRAWL") {
    if (!autoJob.running) {
      sendResponse({ ok: false, error: "Auto-crawl khong chay" });
      return;
    }
    autoJob.stop = true;
    sendResponse({ ok: true, message: "Dang dung sau trang hien tai..." });
    return;
  }
  if (message && message.type === "AUTO_CRAWL_STATUS") {
    sendResponse({
      running: autoJob.running,
      done: autoJob.done,
      total: autoJob.total,
    });
    return;
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
