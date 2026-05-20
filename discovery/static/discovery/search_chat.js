(function () {
  const threadEl = document.getElementById("chat-thread");
  const inputEl = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");
  const sceneList = document.getElementById("scene-list");
  const errEl = document.getElementById("chat-error");
  let sessionId = sessionStorage.getItem("discovery_session_id") || "";
  let typingEl = null;

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return m ? decodeURIComponent(m[2]) : "";
  }

  function appendMsg(role, text) {
    const row = document.createElement("div");
    row.className = "chat-row chat-row--" + role;

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble chat-bubble--" + role;
    bubble.textContent = text;

    row.appendChild(bubble);
    threadEl.appendChild(row);
    threadEl.scrollTop = threadEl.scrollHeight;
  }

  function showTyping() {
    hideTyping();
    const row = document.createElement("div");
    row.className = "chat-typing";
    row.setAttribute("aria-hidden", "true");

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble chat-bubble--assistant";

    for (let i = 0; i < 3; i++) {
      const dot = document.createElement("span");
      dot.className = "chat-typing-dot";
      bubble.appendChild(dot);
    }

    row.appendChild(bubble);
    threadEl.appendChild(row);
    typingEl = row;
    threadEl.scrollTop = threadEl.scrollHeight;
  }

  function hideTyping() {
    if (typingEl && typingEl.parentNode) {
      typingEl.parentNode.removeChild(typingEl);
    }
    typingEl = null;
  }

  function formatScore(score) {
    if (score == null || score === "") return "-";
    return Number(score).toFixed(3);
  }

  function renderScenes(scenes) {
    sceneList.innerHTML = "";
    if (!scenes || !scenes.length) {
      sceneList.innerHTML =
        '<p class="discovery-results-empty">조건에 맞는 장면을 찾지 못했습니다.</p>';
      return;
    }
    scenes.forEach(function (s) {
      const row = document.createElement("article");
      row.className = "scene-row";

      const seriesTitle = s.anime_title || s.anime_id || "알 수 없음";
      const epLabel = s.episode != null ? s.episode + "화" : "-";
      const timeLabel = s.time_label || "-";
      const videoHref =
        (s.video_url || "") + "#t=" + (s.video_start_sec != null ? s.video_start_sec : 0);

      const thumbLink = document.createElement("a");
      thumbLink.className = "scene-row-thumb";
      thumbLink.href = videoHref;
      thumbLink.title = seriesTitle + " " + epLabel + " " + timeLabel + " 재생";
      const img = document.createElement("img");
      img.src = s.thumbnail_url;
      img.alt = seriesTitle + " " + epLabel;
      img.loading = "lazy";
      thumbLink.appendChild(img);

      const body = document.createElement("div");
      body.className = "scene-row-body";

      const titleEl = document.createElement("h3");
      titleEl.className = "scene-row-title";
      titleEl.textContent = seriesTitle;

      const meta = document.createElement("ul");
      meta.className = "scene-row-meta";
      meta.innerHTML =
        "<li><span>화</span> <strong>" +
        epLabel +
        "</strong></li>" +
        "<li><span>시각</span> <strong>" +
        timeLabel +
        "</strong></li>";

      body.appendChild(titleEl);
      body.appendChild(meta);

      const scoreEl = document.createElement("span");
      scoreEl.className = "scene-row-score";
      scoreEl.textContent = formatScore(s.score);

      row.appendChild(thumbLink);
      row.appendChild(body);
      row.appendChild(scoreEl);
      sceneList.appendChild(row);
    });
  }

  async function send() {
    const message = (inputEl.value || "").trim();
    if (!message) return;
    errEl.hidden = true;
    sendBtn.disabled = true;
    inputEl.disabled = true;
    appendMsg("user", message);
    inputEl.value = "";
    showTyping();

    try {
      const res = await fetch("/api/search/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
          message: message,
          session_id: sessionId || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || res.statusText);
      }
      sessionId = data.session_id;
      sessionStorage.setItem("discovery_session_id", sessionId);
      hideTyping();
      appendMsg("assistant", data.reply || "");
      renderScenes(data.scenes || []);
    } catch (e) {
      hideTyping();
      errEl.textContent = e.message || String(e);
      errEl.hidden = false;
    } finally {
      sendBtn.disabled = false;
      inputEl.disabled = false;
      inputEl.focus();
    }
  }

  sendBtn.addEventListener("click", send);
  inputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
})();
