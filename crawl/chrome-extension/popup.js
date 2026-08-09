/*
 * Popup: hien thi ket qua + dieu khien quet.
 *   - Nut "Quet ngay" -> gui AUTO_SCAN toi content script: tu cuon trang
 *     thu thap CONG DON (loc trung), nhan tien trinh qua FB_SCAN_PROGRESS.
 *   - Hien danh sach bai viet co binh luan cong khai (url + trang thai).
 *   - Nut tai file fb_posts_content.txt.
 */

const STORAGE_KEY = "fb_posts";
const POST_COUNT_KEY = "fb_post_count";
const LOAD_WAIT_KEY = "fb_load_wait";

const buttonDownload = document.getElementById("download");
const buttonScan = document.getElementById("scan");
const countInput = document.getElementById("postCount");
const loadWaitInput = document.getElementById("loadWait");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");

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

buttonScan.addEventListener("click", async () => {
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
      await chrome.tabs.sendMessage(tab.id, { type: "PING" });
    } catch (_err) {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    }
    const limit = parseInt(countInput.value, 10) || 5;
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "AUTO_SCAN", limit });
    if (resp && resp.count > 0) {
      setStatus(
        "Group " + (resp.groupId || "?") + ": xong - " + resp.count + " bai (" +
        resp.totalComments + " binh luan). Ngung: " + resp.stopped +
        " sau " + resp.scrolls + " lan cuon. Da luu cong don.",
        "ok"
      );
    } else {
      const dbg = (resp && resp.debug) || {};
      setStatus(
        "Quet xong: KHONG co bai nao co binh luan cong khai." +
        " [debug: group=" + (resp ? resp.groupId : "?") +
        " mountRoots=" + dbg.rootCount + " feed=" + dbg.feedCount +
        " articles=" + dbg.articleCount + " comments=" + dbg.commentCount +
        " containers=" + dbg.containers + " mountPath=" + dbg.mountFound + "]",
        "error"
      );
    }
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

chrome.storage.local.get([STORAGE_KEY, POST_COUNT_KEY, LOAD_WAIT_KEY]).then((data) => {
  if (data[POST_COUNT_KEY]) countInput.value = data[POST_COUNT_KEY];
  if (data[LOAD_WAIT_KEY]) loadWaitInput.value = data[LOAD_WAIT_KEY];
  refreshFromStorage();
});
