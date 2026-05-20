(function () {
  "use strict";

  const ALLOWED_EXT = new Set([".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"]);
  const POLL_MS = 2000;

  const form = document.getElementById("upload-form");
  if (!form) return;

  const videoPicker = document.getElementById("video-picker");
  const videoInput = document.getElementById("video-input");
  const fileNameEl = document.getElementById("video-file-name");
  const fileMetaEl = document.getElementById("video-file-meta");
  const paneYoutube = document.getElementById("source-pane-youtube");
  const paneFile = document.getElementById("source-pane-file");
  const sourceClearBtn = document.getElementById("source-clear-btn");
  const progressWrap = document.getElementById("upload-progress-wrap");
  const progressBar = document.getElementById("upload-progress-bar");
  const progressLabel = document.getElementById("upload-progress-label");
  const progressTrack = progressWrap.querySelector(".progress-track");
  const submitBtn = document.getElementById("upload-submit");
  const resultSection = document.getElementById("upload-result");
  const resultMsg = document.getElementById("upload-result-msg");
  const resultId = document.getElementById("upload-result-id");
  const preview = document.getElementById("upload-preview");
  const youtubeInput = document.getElementById("youtube-url-input");
  const importProgressWrap = document.getElementById("import-progress-wrap");
  const importProgressLabel = document.getElementById("import-progress-label");

  let pollTimer = null;

  function setSubmitEnabled(enabled) {
    submitBtn.disabled = !enabled;
  }

  function setProgress(pct) {
    const v = Math.max(0, Math.min(100, pct));
    progressBar.style.width = v + "%";
    progressLabel.textContent = Math.round(v) + "%";
    progressTrack.setAttribute("aria-valuenow", String(Math.round(v)));
  }

  function formatBytes(n) {
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
    return (n / (1024 * 1024 * 1024)).toFixed(2) + " GB";
  }

  function extOf(name) {
    const i = name.lastIndexOf(".");
    return i >= 0 ? name.slice(i).toLowerCase() : "";
  }

  function activeSource() {
    const hasUrl = youtubeInput.value.trim().length > 0;
    const hasFile = !!(videoInput.files && videoInput.files[0]);
    if (hasUrl) return "youtube";
    if (hasFile) return "file";
    return "none";
  }

  function updateVideoPickUI() {
    const file = videoInput.files && videoInput.files[0];
    if (!file) {
      videoPicker.dataset.state = "empty";
      fileNameEl.textContent = "";
      fileMetaEl.textContent = "";
      videoPicker.classList.remove("video-picker--warn");
      return;
    }
    const ok = ALLOWED_EXT.has(extOf(file.name));
    videoPicker.dataset.state = "picked";
    fileNameEl.textContent = file.name;
    fileMetaEl.textContent = formatBytes(file.size) + (ok ? "" : " · 지원하지 않는 확장자");
    videoPicker.classList.toggle("video-picker--warn", !ok);
  }

  function syncSourceUI() {
    const active = activeSource();
    paneYoutube.classList.toggle("is-active", active === "youtube");
    paneYoutube.classList.toggle("is-dimmed", active === "file");
    paneFile.classList.toggle("is-active", active === "file");
    paneFile.classList.toggle("is-dimmed", active === "youtube");
    sourceClearBtn.hidden = active === "none";
  }

  function clearSources() {
    youtubeInput.value = "";
    videoInput.value = "";
    updateVideoPickUI();
    syncSourceUI();
    youtubeInput.focus();
  }

  function stopPoll() {
    if (!pollTimer) return;
    clearTimeout(pollTimer);
    pollTimer = null;
  }

  function applyJobStatus(data) {
    resultSection.hidden = false;
    resultMsg.textContent = data.message || data.status_display || data.status || "";
    resultId.textContent = data.public_id || "";
    if (data.preview_url) {
      preview.hidden = false;
      preview.src = data.preview_url;
    } else {
      preview.hidden = true;
      preview.removeAttribute("src");
    }
  }

  function pollJobStatus(pollUrl) {
    fetch(pollUrl, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, body: body };
        });
      })
      .then(function (r) {
        if (!r.ok) {
          stopPoll();
          setSubmitEnabled(true);
          alert(r.body.detail || "상태 조회 실패");
          return;
        }
        const data = r.body;
        if (data.status === "importing") {
          importProgressLabel.textContent =
            "YouTube에서 가져오는 중… (" + (data.status_display || data.status) + ")";
          pollTimer = setTimeout(function () {
            pollJobStatus(pollUrl);
          }, POLL_MS);
          return;
        }
        stopPoll();
        importProgressWrap.hidden = true;
        setSubmitEnabled(true);
        if (data.status === "failed") {
          alert(data.last_error || "가져오기 또는 처리에 실패했습니다.");
          applyJobStatus(data);
          return;
        }
        if (data.status === "processing") {
          resultMsg.textContent = "임베딩 처리 중… · " + (data.public_id || "");
        } else if (data.status === "done") {
          resultMsg.textContent = "작업 완료 · " + (data.public_id || "");
        } else if (data.status === "pending" && data.preview_url) {
          resultMsg.textContent = "동영상 준비됨 · 처리 대기/시작 중…";
        }
        applyJobStatus(data);
        resultSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
      })
      .catch(function () {
        pollTimer = setTimeout(function () {
          pollJobStatus(pollUrl);
        }, POLL_MS);
      });
  }

  videoInput.addEventListener("change", function () {
    if (videoInput.files && videoInput.files[0]) {
      youtubeInput.value = "";
    }
    updateVideoPickUI();
    syncSourceUI();
  });

  youtubeInput.addEventListener("input", function () {
    if (youtubeInput.value.trim() && videoInput.files && videoInput.files[0]) {
      videoInput.value = "";
      updateVideoPickUI();
    }
    syncSourceUI();
  });

  sourceClearBtn.addEventListener("click", clearSources);
  syncSourceUI();

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    const hasFile = activeSource() === "file";
    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    xhr.setRequestHeader("Accept", "application/json");

    importProgressWrap.hidden = true;
    progressWrap.hidden = !hasFile;
    if (hasFile) setProgress(0);
    setSubmitEnabled(false);

    xhr.upload.addEventListener("progress", function (e) {
      if (hasFile && e.lengthComputable) {
        setProgress((e.loaded / e.total) * 100);
      }
    });

    xhr.addEventListener("load", function () {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (_) {
        setSubmitEnabled(true);
        alert("서버 응답을 해석할 수 없습니다.");
        return;
      }
      if (xhr.status >= 400) {
        setSubmitEnabled(true);
        alert(data.detail || data.message || "업로드 실패");
        return;
      }
      if (hasFile) setProgress(100);

      if (data.status === "importing" && data.poll_url) {
        importProgressWrap.hidden = false;
        importProgressLabel.textContent = data.message || "YouTube에서 가져오는 중…";
        resultSection.hidden = false;
        resultMsg.textContent = data.message || "";
        resultId.textContent = data.public_id || "";
        preview.hidden = true;
        preview.removeAttribute("src");
        pollJobStatus(data.poll_url);
        return;
      }

      setSubmitEnabled(true);
      applyJobStatus(data);
      resultSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    xhr.addEventListener("error", function () {
      setSubmitEnabled(true);
      alert("네트워크 오류로 업로드에 실패했습니다.");
    });

    xhr.send(new FormData(form));
  });
})();
