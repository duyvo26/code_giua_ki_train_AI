/*
 * Popup: chi HIEN THI ket qua - collection tu dong chay trong content script
 * ngay tai trang group, khong can mo popup.
 *   - Hien danh sach bai viet co binh luan cong khai (url + trang thai).
 *   - Nut tai file fb_posts_content.txt.
 */

const STORAGE_KEY = "fb_posts";
const POST_COUNT_KEY = "fb_post_count";

const buttonDownload = document.getElementById("download");
const buttonDownloadJson = document.getElementById("downloadJson");
const buttonScan = document.getElementById("scan");
const countInput = document.getElementById("postCount");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");

function setStatus(text, className) {
  statusEl.textContent = text;
  statusEl.className = className || "";
}

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

function downloadFile(filename, content) {
  const dataUrl = "data:text/plain;charset=utf-8," + encodeURIComponent(content);
  chrome.downloads.download({ url: dataUrl, filename, saveAs: false });
}function buildOutputText(posts) {
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

function buildOutputJson(posts) {
  return JSON.stringify(
    posts.map((post, index) => ({
      index: index + 1,
      url: post.url,
      postText: post.postText || post.content || "",
      comments: Array.isArray(post.comments) ? post.comments : [],
      commentCount: Array.isArray(post.comments) ? post.comments.length : 0,
    })),
    null,
    2
  );
}

function refreshFromStorage() {
  chrome.storage.local.get(STORAGE_KEY).then((data) => {
    const posts = data[STORAGE_KEY] || [];
    if (posts.length > 0) {
      render(posts);
      buttonDownload.disabled = false;
      buttonDownloadJson.disabled = false;
      buttonDownloadJson.disabled = false;
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

buttonDownloadJson.addEventListener("click", async () => {
  const posts = await downloadPosts();
  if (posts.length === 0) {
    setStatus("Chua co du lieu de tai.", "error");
    return;
  }
  downloadFile("fb_posts_content.json", buildOutputJson(posts));
  setStatus("Da tai fb_posts_content.json (Downloads).", "ok");
});

buttonScan.addEventListener("click", async () => {
  buttonScan.disabled = true;
  setStatus("Dang quet...");
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
    const resp = await chrome.tabs.sendMessage(tab.id, { type: "SCAN_NOW" });
    if (resp && resp.count > 0) {
      setStatus("Group " + (resp.groupId || "?") + ": quet xong - " + resp.count + " bai, " + resp.totalComments + " binh luan cong khai. Da dung.", "ok");
    } else {
      setStatus("Quet xong (da dung): khong co bai nao co binh luan cong khai trong tam nhin. Cuon them roi quet lai.", "error");
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

chrome.storage.local.get([STORAGE_KEY, POST_COUNT_KEY]).then((data) => {
  if (data[POST_COUNT_KEY]) countInput.value = data[POST_COUNT_KEY];
  refreshFromStorage();
});
