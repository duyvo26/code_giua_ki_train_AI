/*
 * Popup: hien thi ket qua + dieu khien quet.
 *   - Nut "Quet 1 trang + gui web" -> gui AUTO_SCAN toi content script: tu
 *     cuon trang thu thap CONG DON (loc trung), gui ve web /api/extension/analyze
 *     kem API key - web tu phan tich cam xuc + tu gui canh bao bot.
 *   - He gio tu web: web tu mo tab ?closetab=true -> content tu quet + gui
 *     web + bao background dong tab (khong can lam gi trong popup).
 *   - Cau hinh web (1 o JSON: webUrl + apiKey) bat buoc truoc khi quet.
 */

const STORAGE_KEY = "fb_posts";
const POST_COUNT_KEY = "fb_post_count";
const LOAD_WAIT_KEY = "fb_load_wait";
const WEB_URL_KEY = "fb_web_url";
const API_KEY_KEY = "fb_api_key";
// Phai khop EXT_VERSION trong content.js - neu cu hon thi re-inject lai
const EXPECTED_EXT_VERSION = 8;

const buttonDownload = document.getElementById("download");
const buttonClear = document.getElementById("clearPosts");
const buttonScan = document.getElementById("scan");
const buttonSaveConfig = document.getElementById("saveConfig");
const countInput = document.getElementById("postCount");
const loadWaitInput = document.getElementById("loadWait");
const webConfigInput = document.getElementById("webConfigJson");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");

// Cau hinh web da luu (nap tu storage luc init, cap nhat khi bam Luu)
let webUrlState = "";
let apiKeyState = "";

/**
 * Hien thi text trang thai + class mau cho vung status cua popup.
 *
 * Logic:
 *   - Ghi textContent truc tiep (an toan, khong injection)
 *   - className mac dinh "" neu khong truyen (reset mau cu)
 *
 * @param {string} text - Noi dung trang thai
 * @param {string} [className] - Class Tailwind mau (vd "ok", "error")
 */
function setStatus(text, className) {
  statusEl.textContent = text;
  statusEl.className = className || "";
}

/**
 * Render danh sach bai viet vao popup (url + badge trang thai + preview).
 *
 * Logic:
 *   - Moi bai tao 3 the: url, badge (LOI / DA LAY NOI DUNG / CHUA LAY),
 *     preview 120 ky tu dong dau cua content
 *   - Doi mau badge theo trang thai: error/wait/ok
 *
 * @param {Array} posts - Danh sach bai tu chrome.storage.local
 */
function render(posts) {
  resultEl.innerHTML = "";
  (posts || []).forEach((post) => {
    const div = document.createElement("div");
    div.className = "item";
    const urlDiv = document.createElement("div");
    urlDiv.className = "url";
    urlDiv.textContent = post.url;
    const status = document.createElement("div");
    status.className = "badge " + (post.error ? "badge-error" : post.content ? "badge-ok" : "badge-wait");
    status.textContent = post.error
      ? "LOI: " + post.error
      : post.content
        ? "DA LAY NOI DUNG (" + post.content.length + " ky tu" +
          (post.commentCount ? ", " + post.commentCount + " binh luan" : "") + ")"
        : "CHUA LAY NOI DUNG";
    const preview = document.createElement("div");
    preview.className = "preview";
    preview.textContent = post.content ? post.content.split("\n")[0].slice(0, 120) : "";
    div.appendChild(urlDiv);
    div.appendChild(status);
    div.appendChild(preview);
    resultEl.appendChild(div);
  });
}

/**
 * Tai 1 file text xuong Downloads bang data URL.
 *
 * Logic:
 *   - Ma hoa content thanh data:text/plain UTF-8 qua encodeURIComponent
 *   - Goi chrome.downloads.download (khong hien hop thoai saveAs)
 *
 * @param {string} filename - Ten file xuat ra (vd fb_posts_content.txt)
 * @param {string} content - Noi dung file
 */
function downloadFile(filename, content) {
  const dataUrl = "data:text/plain;charset=utf-8," + encodeURIComponent(content);
  chrome.downloads.download({ url: dataUrl, filename, saveAs: false });
}

/**
 * Dung text tai file: dinh dang TXT chuan (=== BAI N ===, URL, NOI DUNG, BINH LUAN).
 *
 * Logic:
 *   - Binh luan: uu tien post.comments, fallback trich tu post.content
 *     (bo dong "--- BINH LUAN CONG KHAI ---" va dong trong)
 *   - Noi dung bai: post.postText hoac content, moi dong them tien to 2 khoang trang
 *
 * @param {Array} posts - Danh sach bai viet
 * @returns {string} Noi dung file TXT
 */
function buildOutputText(posts) {
  return posts.map((post, index) => {
    const comments = Array.isArray(post.comments) && post.comments.length > 0
      ? post.comments.map((c, i) => (i + 1) + ". " + c).join("\n")
      : post.content
        ? post.content.split("\n").filter((l) => l && !l.startsWith("---")).slice(1).map((l, i) => (i + 1) + ". " + l).join("\n")
        : "(khong co binh luan)";
    const body = post.postText || post.content || "(khong lay duoc noi dung)";
    return [
      "=== BAI " + (index + 1) + " ===",
      "URL: " + post.url,
      "NOI DUNG:",
      body.split("\n").map((l) => "  " + l).join("\n"),
      "--- BINH LUAN ---",
      comments,
      "",
    ].join("\n");
  }).join("\n");
}

/**
 * Doc bai viet tu storage va render lai popup.
 *
 * Logic:
 *   - Co bai: render danh sach, mo nut tai file, in tong so binh luan
 *   - Khong co: hien huong dan mo trang group (khong phai loi)
 */
function refreshFromStorage() {
  chrome.storage.local.get(STORAGE_KEY).then((data) => {
    const posts = data[STORAGE_KEY] || [];
    if (posts.length > 0) {
      render(posts);
      buttonDownload.disabled = false;
      const totalComments = posts.reduce((sum, p) => sum + (p.commentCount || 0), 0);
      setStatus(
        "Da co " + posts.length + " bai viet, tong " + totalComments + " binh luan cong khai.",
        "ok"
      );
    } else {
      setStatus("Chua co du lieu. Mo/lam moi (F5) trang group bat ky.", "error");
    }
  }).catch(() => {});
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[STORAGE_KEY]) {
    refreshFromStorage();
  }
});

/**
 * Lay danh sach bai viet dang luu trong storage.
 *
 * @returns {Promise<Array>} Danh sach bai (rong neu chua co)
 */
function downloadPosts() {
  return chrome.storage.local.get(STORAGE_KEY).then((data) => data[STORAGE_KEY] || []);
}

buttonDownload.addEventListener("click", async () => {
  const posts = await downloadPosts();
  if (posts.length === 0) {
    setStatus("Chua co du lieu de tai.", "error");
    return;
  }
  downloadFile("fb_posts_content.txt", buildOutputText(posts));
  setStatus("Da tai fb_posts_content.txt (Downloads).", "ok");
});

/**
 * Xoa toan bo bai viet cu da luu trong storage (reset cong don).
 *
 * Logic:
 *   - Hoi xac nhan truoc khi xoa (khong the khoi phuc)
 *   - chrome.storage.local.remove(STORAGE_KEY) -> content script lang nghe
 *     onChanged se reset lastSavedSignature de quet lai tu dau duoc
 *   - Render lai popup ve trang thai "chua co du lieu"
 */
buttonClear.addEventListener("click", () => {
  if (!confirm("Xoa toan bo bai viet cu da luu trong extension?")) return;
  chrome.storage.local.remove(STORAGE_KEY).then(() => {
    setStatus("Da xoa toan bo bai cu.", "ok");
    refreshFromStorage();
  });
});

/**
 * Nhan tien trinh auto-scroll tu content script (FB_SCAN_PROGRESS).
 *
 * Logic:
 *   - Content script gui sau moi lan luu (count = so bai da gop)
 *   - Popup chi cap nhat status; danh sach tu render qua storage.onChanged
 */
chrome.runtime.onMessage.addListener((message) => {
  if (message && message.type === "FB_SCAN_PROGRESS") {
    setStatus(
      "Dang cuon & thu thap... " + message.count + " bai, " +
      message.totalComments + " binh luan (lan cuon " + (message.scrolls || 1) + ")",
      "ok"
    );
  }
});

/**
 * Gui danh sach bai viet ve web /api/extension/analyze kem API key.
 *
 * Logic:
 *   - POST JSON {posts} + header X-API-Key (web bat buoc kiem tra)
 *   - Web tra ngay {ok, message, received_posts} - phan tich chay thread nen
 *   - Loi HTTP (401 key sai, 500 chua train model...) -> throw Error(message)
 *
 * @param {Array} posts - Danh sach bai tu AUTO_SCAN ({url, postText, comments})
 * @returns {Promise<Object>} Phan hoi tu web
 */
async function sendToWeb(posts) {
  const webUrl = webUrlState.trim().replace(/\/+$/, "");
  const resp = await fetch(webUrl + "/api/extension/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKeyState },
    body: JSON.stringify({ posts }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || ("HTTP " + resp.status));
  return data;
}

/**
 * Luu cau hinh web: parse JSON tu 1 o duy nhat roi luu vao storage.
 *
 * Logic:
 *   - Nhan dang {"webUrl": "...", "apiKey": "..."} (copy tu web - nut Copy config)
 *   - JSON loi / thieu truong -> bao loi ro, khong ghi de config cu
 *   - Thanh cong: cap nhat webUrlState/apiKeyState + chrome.storage
 *
 * @returns {Promise<void>}
 */
async function saveWebConfig() {
  const raw = webConfigInput.value.trim();
  if (!raw) {
    setStatus("Dan JSON cau hinh vao o tren (lay tu web - nut Copy config).", "error");
    return;
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    setStatus("JSON khong hop le: " + err.message, "error");
    return;
  }
  const webUrl = String(parsed.webUrl || parsed.url || "").trim();
  const apiKey = String(parsed.apiKey || parsed.key || "").trim();
  if (!webUrl || !apiKey) {
    setStatus("Thieu webUrl hoac apiKey trong JSON.", "error");
    return;
  }
  webUrlState = webUrl;
  apiKeyState = apiKey;
  await chrome.storage.local.set({ [WEB_URL_KEY]: webUrl, [API_KEY_KEY]: apiKey });
  webConfigInput.value = "";
  setStatus("Da luu cau hinh web. Bam Quet ngay de bat dau.", "ok");
}

buttonSaveConfig.addEventListener("click", saveWebConfig);

buttonScan.addEventListener("click", async () => {
  if (!webUrlState || !apiKeyState) {
    setStatus("Cau hinh web truoc (dan JSON tu web vao o phia tren roi Luu).", "error");
    return;
  }
  buttonScan.disabled = true;
  setStatus("Dang cuon & thu thap...", "ok");
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs && tabs.length > 0 ? tabs[0] : null;
    if (!tab || !tab.url || !tab.url.includes("facebook.com/groups/")) {
      setStatus("Tab hien tai KHONG phai trang group - mo group roi bam Quet.", "error");
      return;
    }
    try {
      let ping;
      try {
        ping = await chrome.tabs.sendMessage(tab.id, { type: "PING" });
      } catch (_err) {
        ping = null; // content script chua duoc inject
      }
      // Content script cu (sau khi reload extension ma chua F5 tab) se khong
      // hieu AUTO_SCAN -> tu inject lai ban moi roi quet tiep
      if (!ping || ping.version !== EXPECTED_EXT_VERSION) {
        await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      }
    } catch (err) {
      setStatus("Khong inject duoc content script: " + err.message, "error");
      return;
    }
    const limit = parseInt(countInput.value, 10) || 5;
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "AUTO_SCAN", limit });
    if (resp === null || resp === undefined) {
      setStatus(
        "Khong nhan duoc phan hoi tu trang. Vao chrome://extensions bam Reload " +
        "extension, roi F5 lai trang group.",
        "error"
      );
      return;
    }
    if (!resp.count) {
      const dbg = (resp && resp.debug) || {};
      setStatus(
        "Quet xong: KHONG co bai nao co binh luan cong khai." +
        " [debug: group=" + (resp.groupId || "?") +
        " mountRoots=" + dbg.rootCount + " feed=" + dbg.feedCount +
        " articles=" + dbg.articleCount + " comments=" + dbg.commentCount +
        " containers=" + dbg.containers + " mountPath=" + dbg.mountFound + "]",
        "error"
      );
      return;
    }
    setStatus("Quet xong " + resp.count + " bai - dang gui ve web...", "ok");
    let sent;
    try {
      sent = await sendToWeb(resp.posts);
    } catch (err) {
      setStatus(
        "Quet xong " + resp.count + " bai (da luu) NHUNG gui web LOI: " + err.message,
        "error"
      );
      return;
    }
    setStatus(
      "Web da nhan " + (sent.received_posts || resp.count) + " bai - " +
      (sent.message || "dang phan tich + tu gui canh bao bot..."),
      "ok"
    );
  } catch (err) {
    setStatus("Loi quet: " + err.message, "error");
  } finally {
    buttonScan.disabled = false;
  }
});

countInput.addEventListener("change", () => {
  const value = parseInt(countInput.value, 10);
  if (!value || value < 1) {
    countInput.value = 5;
    setStatus("So bai phai >= 1 - dat lai 5.", "error");
    return;
  }
  chrome.storage.local.set({ [POST_COUNT_KEY]: value }).then(() => {
    setStatus("Se tim " + value + " bai co binh luan. Ap dung tu lan quet tiep theo.", "ok");
  });
});

loadWaitInput.addEventListener("change", () => {
  const value = parseInt(loadWaitInput.value, 10);
  if (!value || value < 500 || value > 10000) {
    loadWaitInput.value = 3000;
    setStatus("Thoi gian cho load phai trong 500-10000ms - dat lai 3000.", "error");
    return;
  }
  chrome.storage.local.set({ [LOAD_WAIT_KEY]: value }).then(() => {
    setStatus("Thoi gian cho load moi lan cuon: " + value + "ms. Ap dung tu lan quet tiep theo.", "ok");
  });
});

chrome.storage.local.get([
  STORAGE_KEY, POST_COUNT_KEY, LOAD_WAIT_KEY, WEB_URL_KEY, API_KEY_KEY,
]).then((data) => {
  if (data[POST_COUNT_KEY]) countInput.value = data[POST_COUNT_KEY];
  if (data[LOAD_WAIT_KEY]) loadWaitInput.value = data[LOAD_WAIT_KEY];
  if (data[WEB_URL_KEY]) webUrlState = data[WEB_URL_KEY];
  if (data[API_KEY_KEY]) apiKeyState = data[API_KEY_KEY];
  refreshFromStorage();
});
