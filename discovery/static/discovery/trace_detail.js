(function () {
  "use strict";

  var dataEl = document.getElementById("trace-payload");
  if (!dataEl) {
    return;
  }
  if (typeof JSONFormatter === "undefined") {
    var root = document.getElementById("trace-payload-root");
    if (root) {
      root.textContent = "JSON 뷰어 스크립트를 불러오지 못했습니다. static 파일을 확인하세요.";
    }
    return;
  }

  var payload;
  try {
    payload = JSON.parse(dataEl.textContent);
  } catch (err) {
    var failRoot = document.getElementById("trace-payload-root");
    if (failRoot) {
      failRoot.textContent = "payload JSON 파싱 실패: " + err;
    }
    return;
  }

  var stages = Array.isArray(payload.stages) ? payload.stages : [];

  function renderTree(container, json, openDepth) {
    if (!container) return;
    container.textContent = "";
    var formatter = new JSONFormatter(json, openDepth);
    container.appendChild(formatter.render());
    return formatter;
  }

  stages.forEach(function (stage, index) {
    var el = document.querySelector('.json-tree[data-stage-index="' + index + '"]');
    if (el) {
      renderTree(el, stage.data || {}, 1);
    }
  });

  var payloadRoot = document.getElementById("trace-payload-root");
  var payloadFormatter = renderTree(payloadRoot, payload, 2);

  var copyBtn = document.getElementById("trace-copy-json");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var text = JSON.stringify(payload, null, 2);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () {
            copyBtn.textContent = "복사됨";
            setTimeout(function () {
              copyBtn.textContent = "Copy JSON";
            }, 1500);
          },
          function () {
            window.prompt("JSON 복사:", text);
          }
        );
      } else {
        window.prompt("JSON 복사:", text);
      }
    });
  }

  var expandBtn = document.getElementById("trace-expand-all");
  if (expandBtn && payloadFormatter) {
    expandBtn.addEventListener("click", function () {
      payloadFormatter.openAtDepth(Infinity);
    });
  }

  var collapseBtn = document.getElementById("trace-collapse-all");
  if (collapseBtn && payloadFormatter) {
    collapseBtn.addEventListener("click", function () {
      payloadFormatter.openAtDepth(0);
    });
  }
})();
