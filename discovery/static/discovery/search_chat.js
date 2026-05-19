(function () {
  const logEl = document.getElementById("chat-log");
  const inputEl = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");
  const sceneList = document.getElementById("scene-list");
  const errEl = document.getElementById("chat-error");
  let sessionId = sessionStorage.getItem("discovery_session_id") || "";

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return m ? decodeURIComponent(m[2]) : "";
  }

  function appendMsg(role, text) {
    const div = document.createElement("div");
    div.className = "msg msg-" + (role === "user" ? "user" : "bot");
    div.textContent = (role === "user" ? "나: " : "AI: ") + text;
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function renderScenes(scenes) {
    sceneList.innerHTML = "";
    if (!scenes || !scenes.length) {
      sceneList.innerHTML = "<p class=\"muted\">아직 결과가 없습니다.</p>";
      return;
    }
    scenes.forEach(function (s) {
      const card = document.createElement("article");
      card.className = "scene-card";
      const title = (s.anime_title || s.anime_id) + " · " + (s.episode || "?") + "화 · " + (s.time_label || "");
      const img = document.createElement("img");
      img.src = s.thumbnail_url;
      img.alt = title;
      img.loading = "lazy";
      const meta = document.createElement("p");
      meta.className = "scene-meta";
      meta.textContent = title + " (유사도 " + (s.score != null ? s.score : "-") + ")";
      const video = document.createElement("video");
      video.controls = true;
      video.preload = "metadata";
      video.src = s.video_url + "#t=" + (s.video_start_sec || 0);
      card.appendChild(img);
      card.appendChild(meta);
      card.appendChild(video);
      sceneList.appendChild(card);
    });
  }

  async function send() {
    const message = (inputEl.value || "").trim();
    if (!message) return;
    errEl.hidden = true;
    sendBtn.disabled = true;
    appendMsg("user", message);
    inputEl.value = "";

    try {
      const res = await fetch("/api/search/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({ message: message, session_id: sessionId || undefined }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || res.statusText);
      }
      sessionId = data.session_id;
      sessionStorage.setItem("discovery_session_id", sessionId);
      appendMsg("bot", data.reply || "");
      renderScenes(data.scenes || []);
    } catch (e) {
      errEl.textContent = e.message || String(e);
      errEl.hidden = false;
    } finally {
      sendBtn.disabled = false;
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
