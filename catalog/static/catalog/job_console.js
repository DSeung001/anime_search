(function () {
  "use strict";

  var POLL_OK_MS = 2000;
  var BACKOFF_INITIAL_MS = 1000;
  var BACKOFF_MAX_MS = 30000;
  var MAX_POLL_FAILURES = 3;
  var ACTIVE_STATUSES = { pending: true, processing: true };

  var root = document.getElementById("job-console-root");
  if (!root) return;

  var runJobUrlTemplate = root.getAttribute("data-run-job-url-template");
  var jobListUrl = root.getAttribute("data-job-list-url");
  var deleteJobUrlTemplate = root.getAttribute("data-delete-job-url-template");
  var csrfToken = root.getAttribute("data-csrf-token");

  var statusLabels = {
    pending: "대기",
    processing: "처리 중",
    done: "완료",
    failed: "실패",
  };

  var UUID_PLACEHOLDER = "00000000-0000-0000-0000-000000000000";

  var pollTimer = null;
  var pollFailCount = 0;
  var pollStopped = false;
  var msgEl = document.getElementById("job-console-msg");

  function setMessage(text, kind) {
    if (!msgEl) return;
    msgEl.textContent = text || "";
    msgEl.className = "job-console-flash" + (kind ? " " + kind : "");
    if (!text) msgEl.className = "job-console-flash";
  }

  function nextBackoffMs(failCount) {
    var ms = BACKOFF_INITIAL_MS * Math.pow(2, Math.max(0, failCount - 1));
    return Math.min(ms, BACKOFF_MAX_MS);
  }

  function rowForPublicId(publicId) {
    return document.querySelector('tr[data-public-id="' + publicId + '"]');
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/"/g, "&quot;");
  }

  function truncate(s, n) {
    if (s.length <= n) return s;
    return s.slice(0, n - 1) + "…";
  }

  function withPublicId(template, publicId) {
    return template.replace(UUID_PLACEHOLDER, publicId);
  }

  function fetchJson(url, options) {
    options = options || {};
    options.credentials = "same-origin";
    options.headers = options.headers || {};
    if (options.method && options.method !== "GET") {
      options.headers["X-CSRFToken"] = csrfToken;
      options.headers["Content-Type"] = "application/json";
    }
    options.headers["Accept"] = "application/json";
    return fetch(url, options).then(function (res) {
      return res.text().then(function (text) {
        var body = {};
        if (text) {
          try {
            body = JSON.parse(text);
          } catch (e) {
            body = { detail: text };
          }
        }
        return { ok: res.ok, status: res.status, body: body };
      });
    });
  }

  function updateRow(row, data) {
    if (!row) return;
    var prevStatus = row.getAttribute("data-status");
    var status = data.status;
    row.setAttribute("data-status", status);
    row.classList.remove(
      "job-row--failed",
      "job-row--processing",
      "job-row--done",
      "job-row--pending"
    );
    if (status === "failed") row.classList.add("job-row--failed");
    else if (status === "processing") row.classList.add("job-row--processing");
    else if (status === "done") row.classList.add("job-row--done");
    else if (status === "pending") row.classList.add("job-row--pending");

    var badge = row.querySelector(".job-status-badge");
    if (badge) {
      badge.className = "badge job-status-badge badge-" + status;
      badge.textContent = data.status_display || statusLabels[status] || status;
      badge.removeAttribute("title");
    }

    var errCell = row.querySelector(".job-error-cell");
    if (errCell) {
      var err = data.last_error || "";
      if (err) {
        errCell.innerHTML =
          '<span class="job-error-text" title="' +
          escapeAttr(err) +
          '">' +
          escapeHtml(truncate(err, 40)) +
          "</span>";
      } else {
        errCell.textContent = "—";
      }
    }

    if (prevStatus && prevStatus !== status) {
      notifyTransition(data.public_id, prevStatus, status, data.last_error);
    }
  }

  function notifyTransition(publicId, fromStatus, toStatus, lastError) {
    var shortId = (publicId || "").slice(0, 8);
    if (fromStatus === "pending" && toStatus === "processing") {
      setMessage("처리 시작 (" + shortId + "…)", "info");
    } else if (toStatus === "done") {
      setMessage("작업 완료 (" + shortId + "…)", "success");
    } else if (toStatus === "failed") {
      setMessage(
        "작업 실패: " + truncate(lastError || shortId, 80),
        "error"
      );
    }
  }

  function hasActiveJobsInTable() {
    var rows = document.querySelectorAll("#jobs-table tbody tr[data-public-id]");
    for (var i = 0; i < rows.length; i++) {
      var st = rows[i].getAttribute("data-status");
      if (ACTIVE_STATUSES[st]) return true;
    }
    return false;
  }

  function stopListPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function scheduleListPoll(delayMs) {
    stopListPolling();
    if (pollStopped) return;
    pollTimer = window.setTimeout(pollListOnce, delayMs);
  }

  function ensureListPolling() {
    if (pollStopped) return;
    if (hasActiveJobsInTable()) {
      scheduleListPoll(POLL_OK_MS);
    } else {
      stopListPolling();
    }
  }

  function startListPolling() {
    pollStopped = false;
    pollFailCount = 0;
    pollListOnce();
  }

  function pollListOnce() {
    if (pollStopped || !jobListUrl) return;

    fetchJson(jobListUrl)
      .then(function (result) {
        if (pollStopped) return;
        if (!result.ok) {
          pollFailCount += 1;
          if (pollFailCount >= MAX_POLL_FAILURES) {
            pollStopped = true;
            stopListPolling();
            setMessage("상태 목록 확인 실패 — 새로고침하세요.", "error");
            return;
          }
          scheduleListPoll(nextBackoffMs(pollFailCount));
          return;
        }

        pollFailCount = 0;
        var jobs = result.body.jobs || [];
        var activeInResponse = false;

        jobs.forEach(function (job) {
          var row = rowForPublicId(job.public_id);
          if (row) {
            updateRow(row, job);
          }
          if (ACTIVE_STATUSES[job.status]) activeInResponse = true;
        });

        if (activeInResponse || hasActiveJobsInTable()) {
          scheduleListPoll(POLL_OK_MS);
        } else {
          stopListPolling();
        }
      })
      .catch(function () {
        if (pollStopped) return;
        pollFailCount += 1;
        if (pollFailCount >= MAX_POLL_FAILURES) {
          pollStopped = true;
          stopListPolling();
          setMessage("네트워크 오류로 상태 확인 중단", "error");
          return;
        }
        scheduleListPoll(nextBackoffMs(pollFailCount));
      });
  }

  function runJobUrl(publicId) {
    return withPublicId(runJobUrlTemplate, publicId);
  }

  function deleteJobUrl(publicId) {
    return withPublicId(deleteJobUrlTemplate, publicId);
  }

  var DELETE_BLOCKED_MSG = "처리 중인 작업은 삭제할 수 없습니다.";

  function isJobRowProcessing(row) {
    return row && row.getAttribute("data-status") === "processing";
  }

  function onDeleteJob(ev) {
    var btn = ev.target.closest(".job-delete-btn");
    if (!btn) return;

    var row = btn.closest("tr[data-public-id]");
    if (isJobRowProcessing(row)) {
      window.alert(DELETE_BLOCKED_MSG);
      return;
    }

    var publicId = btn.getAttribute("data-public-id");
    if (!publicId) return;

    if (
      !window.confirm(
        "이 작업과 Qdrant·스테이징·(해당 시) 캐논 프레임 데이터를 삭제합니다. 계속할까요?"
      )
    ) {
      return;
    }

    btn.disabled = true;
    setMessage("삭제 중…", "info");

    fetchJson(deleteJobUrl(publicId), { method: "POST", body: "{}" })
      .then(function (result) {
        if (!result.ok) {
          btn.disabled = false;
          var detail = result.body.detail || "삭제 실패";
          if (result.status === 409) {
            window.alert(detail);
          }
          setMessage(detail, "error");
          return;
        }
        var row = rowForPublicId(publicId);
        if (row) row.remove();
        var tbody = document.querySelector("#jobs-table tbody");
        if (tbody && !tbody.querySelector("tr[data-public-id]")) {
          var empty = document.createElement("tr");
          empty.innerHTML = '<td colspan="7" class="empty">작업 없음</td>';
          tbody.appendChild(empty);
        }
        setMessage("삭제했습니다.", "success");
        ensureListPolling();
      })
      .catch(function () {
        btn.disabled = false;
        setMessage("네트워크 오류", "error");
      });
  }

  function onRunJob(ev) {
    ev.preventDefault();
    var form = ev.target;
    var raw = (form.querySelector('[name="job_public_id"]') || {}).value;
    var publicId = String(raw || "").trim();
    if (!publicId) {
      setMessage("UUID를 입력하세요.", "error");
      return;
    }

    var btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = true;
    setMessage("큐에 넣는 중…", "info");

    fetchJson(runJobUrl(publicId), { method: "POST", body: "{}" })
      .then(function (result) {
        if (btn) btn.disabled = false;
        if (!result.ok) {
          setMessage(result.body.detail || "실행 요청 실패", "error");
          return;
        }
        setMessage("워커에 넣었습니다.", "success");
        var row = rowForPublicId(publicId);
        if (row) {
          updateRow(row, {
            public_id: publicId,
            status: "processing",
            status_display: statusLabels.processing,
            last_error: "",
          });
        }
        startListPolling();
      })
      .catch(function () {
        if (btn) btn.disabled = false;
        setMessage("네트워크 오류", "error");
      });
  }

  var formRunJob = document.getElementById("form-run-job");
  if (formRunJob) formRunJob.addEventListener("submit", onRunJob);

  var jobsTable = document.getElementById("jobs-table");
  if (jobsTable) jobsTable.addEventListener("click", onDeleteJob);

  if (hasActiveJobsInTable()) {
    startListPolling();
  }
})();
