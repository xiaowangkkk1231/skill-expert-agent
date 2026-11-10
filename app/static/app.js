(function () {
  "use strict";

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var toastTimer = null;
  function toast(msg) {
    var el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("on"); }, 2600);
  }
  window.toast = toast;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  var TYPE_LABEL = {
    constraint: "禁令", preference: "偏好", workflow: "步骤", example: "样例"
  };

  /* ================= 提炼页 ================= */
  function initPlay() {
    var conv = $("#conv");
    var charCount = $("#charCount");
    var runBtn = $("#runBtn");
    var clearBtn = $("#clearBtn");
    var runStatus = $("#runStatus");
    var baseId = ($("#baseSkillId") || {}).value || "";

    var state = { signals: [], clusters: {}, skill: {}, runId: null, format: "claude-code", saved: null };

    function updateCount() {
      var n = conv.value.trim().length;
      charCount.textContent = n + " 字";
      charCount.style.color = n > 60000 ? "var(--red)" : "";
    }
    conv.addEventListener("input", updateCount);
    updateCount();

    $$("#sampleChips .chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        conv.value = chip.dataset.text || "";
        $$("#sampleChips .chip").forEach(function (c) { c.classList.remove("on"); });
        chip.classList.add("on");
        updateCount();
      });
    });

    clearBtn.addEventListener("click", function () {
      conv.value = "";
      updateCount();
      resetAll();
      runStatus.textContent = "";
    });

    function act(name) { return $('.act[data-act="' + name + '"]'); }
    function setAct(name, cls, label) {
      var el = act(name);
      if (!el) return;
      el.classList.remove("running", "done");
      if (cls) el.classList.add(cls);
      var st = el.querySelector(".act-state");
      if (st && label) st.textContent = label;
    }

    function resetAll() {
      state = { signals: [], clusters: {}, skill: {}, runId: null, format: "claude-code", saved: null };
      $("#signalsList").innerHTML = "";
      $("#signalsEmpty").style.display = "";
      $("#buckets").innerHTML = "";
      $("#mapping").innerHTML = '<span class="hint">四类要求 → SKILL.md 的四段正文。</span>';
      $("#fieldName").textContent = "—";
      $("#fieldDesc").textContent = "—";
      $("#bodyPre").textContent = "";
      $("#lights").innerHTML = "";
      $("#issues").innerHTML = "";
      $("#resultPanel").style.display = "none";
      $("#libraryLink").style.display = "none";
      ["signals", "clusters", "mapping", "compose", "lint"].forEach(function (n) {
        setAct(n, "", "待运行");
      });
      $("#actHint").textContent = "等待输入";
    }

    /* ---- 渲染 ---- */
    function addSignal(s) {
      var row = document.createElement("div");
      row.className = "sig" + (s.verified ? "" : " sig-unverified");
      var t = TYPE_LABEL[s.type] || s.type;
      row.innerHTML =
        '<span class="type t-' + esc(s.type) + '">' + esc(t) + "</span>" +
        '<div style="min-width:0"><div>' + esc(s.text) + "</div>" +
        '<div class="sig-quote">' + esc(s.quote) + "</div></div>";
      $("#signalsList").appendChild(row);
      $("#signalsEmpty").style.display = "none";
    }

    function renderBuckets() {
      var order = [["constraints", "禁令"], ["workflows", "步骤"], ["preferences", "偏好"], ["examples", "样例"]];
      var html = "";
      order.forEach(function (pair) {
        var items = state.clusters[pair[0]] || [];
        if (!items.length) return;
        html += '<div class="bucket"><div class="bucket-head"><span>' + pair[1] +
          "</span><span>" + items.length + "</span></div><ul>" +
          items.map(function (i) { return "<li>" + esc(i) + "</li>"; }).join("") +
          "</ul></div>";
      });
      $("#buckets").innerHTML = html || '<div class="hint">没有可归档的要求。</div>';
    }

    function renderMapping() {
      var rows = [
        ["禁令", (state.clusters.constraints || []).length, "## 必须避免"],
        ["偏好", (state.clusters.preferences || []).length, "## 风格要求"],
        ["步骤", (state.clusters.workflows || []).length, "## 工作流"],
        ["样例", (state.clusters.examples || []).length, "## 示例对照"]
      ];
      var total = rows.reduce(function (a, r) { return a + r[1]; }, 0);
      var html = '<div class="hint" style="margin-bottom:8px">' + state.signals.length +
        " 条要求 → " + total + " 条规则 → body 四段</div>";
      html += '<table class="rule-table"><tbody>';
      rows.forEach(function (r) {
        html += "<tr><td>" + r[0] + '</td><td class="mono">' + r[2] + "</td><td style=\"text-align:right\">" + r[1] + " 条</td></tr>";
      });
      html += "</tbody></table>";
      $("#mapping").innerHTML = html;
    }

    function renderLights(byField) {
      var order = [["name", "命名"], ["description", "描述焦点"], ["body", "正文结构"], ["signals", "原话溯源"]];
      $("#lights").innerHTML = order.map(function (p) {
        var lv = byField[p[0]] || "ok";
        var txt = lv === "ok" ? "通过" : lv === "warn" ? "注意" : "不合规";
        return '<div class="light ' + lv + '"><i></i>' + p[1] + " · " + txt + "</div>";
      }).join("");
    }

    function renderIssues(issues) {
      if (!issues.length) {
        $("#issues").innerHTML = '<div class="hint" style="color:var(--teal)">全部通过 —— 这份可以直接拿走用。</div>';
        return;
      }
      $("#issues").innerHTML = issues.map(function (i) {
        return '<div class="issue ' + i.level + '"><span class="tag">' + esc(i.rule) + "</span><div>" +
          esc(i.message) + (i.hint ? '<div class="issue-hint">' + esc(i.hint) + "</div>" : "") +
          "</div></div>";
      }).join("");
    }

    /* ---- SSE ---- */
    function subscribe(runId) {
      var es = new EventSource("/api/runs/" + runId + "/stream");

      es.addEventListener("stage", function (e) {
        var d = JSON.parse(e.data);
        var map = {
          signals: "signals", clusters: "clusters", compose: "compose", lint: "lint"
        };
        var name = map[d.stage];
        if (!name) return;
        if (d.status === "running") {
          setAct(name, "running", "进行中");
          $("#actHint").textContent = name === "signals" ? "正在挑要求…" : "处理中…";
        } else {
          var meta = d.meta || {};
          var label = "完成";
          if (name === "signals") label = (meta.count || 0) + " 条要求";
          if (name === "clusters") label = (meta.total || 0) + " 条规则";
          setAct(name, "done", label);
          if (name === "signals") { setAct("clusters", "running", "进行中"); renderMapping(); }
          if (name === "clusters") { setAct("mapping", "done", "已落格"); setAct("compose", "running", "进行中"); }
          if (name === "compose") setAct("lint", "running", "进行中");
        }
      });

      es.addEventListener("signal", function (e) {
        var s = JSON.parse(e.data);
        state.signals.push(s);
        addSignal(s);
      });

      es.addEventListener("cluster", function (e) {
        var d = JSON.parse(e.data);
        state.clusters[d.bucket] = d.items || [];
        renderBuckets();
      });

      es.addEventListener("field", function (e) {
        var d = JSON.parse(e.data);
        if (d.field === "name") { $("#fieldName").textContent = d.value; state.skill.name = d.value; }
        if (d.field === "description") { $("#fieldDesc").textContent = d.value; state.skill.description = d.value; }
        if (d.field === "body_done") { state.skill.body = d.value; renderMapping(); }
      });

      es.addEventListener("delta", function (e) {
        var d = JSON.parse(e.data);
        var pre = $("#bodyPre");
        pre.textContent += d.chunk;
        pre.scrollTop = pre.scrollHeight;
      });

      es.addEventListener("diff", function (e) {
        var d = JSON.parse(e.data);
        var html = '<div class="hint" style="margin-top:12px">相对 v' + d.base_version + " 的变化</div>";
        html += d.entries.map(function (x) {
          var sign = x.kind === "added" ? "+" : x.kind === "modified" ? "~" : "?";
          var color = x.kind === "added" ? "var(--teal)" : x.kind === "modified" ? "var(--amber)" : "var(--ink3)";
          return '<div class="sig"><span class="type" style="background:#f4f7f5;color:' + color + '">' + sign +
            "</span><div>" + esc(x.text) + (x.old ? '<div class="sig-quote">原：' + esc(x.old) + "</div>" : "") + "</div></div>";
        }).join("");
        $("#mapping").insertAdjacentHTML("beforeend", html);
      });

      es.addEventListener("lint", function (e) {
        var d = JSON.parse(e.data);
        renderLights(d.by_field || {});
        renderIssues(d.issues || []);
        setAct("lint", "done", d.level === "ok" ? "全绿" : d.level === "warn" ? "有提醒" : "不合规");
      });

      es.addEventListener("notice", function (e) {
        toast(JSON.parse(e.data).message);
      });

      es.addEventListener("error", function (e) {
        if (!e.data) return;
        var d = JSON.parse(e.data);
        toast(d.message || "处理失败");
        runStatus.textContent = "失败";
        finishUI();
      });

      es.addEventListener("done", function (e) {
        var d = JSON.parse(e.data);
        $("#actHint").textContent = "跑完了";
        runStatus.textContent = "";
        setAct("compose", "done", "已生成");
        setAct("lint", "done", d.lint === "ok" ? "全绿" : "有提醒");
        $("#resultPanel").style.display = "";
        $("#resultHint").textContent = d.signals + " 条信号 · " + d.clusters + " 条规则 · " + d.provider;
        loadPreview();
        finishUI();
        es.close();
      });

      es.onerror = function () {
        // EventSource 会自动重连，这里只做提示
        if (es.readyState === 2) finishUI();
      };
    }

    function finishUI() {
      runBtn.disabled = false;
      runBtn.textContent = "再跑一遍";
    }

    /* ---- 预览 / 导出 ---- */
    function loadPreview() {
      if (!state.runId) return;
      fetch("/api/runs/" + state.runId + "/preview?format=" + state.format)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.detail) { $("#exportPreview").textContent = d.detail; return; }
          $("#exportPreview").textContent = d.content;
          $("#exportHint").textContent = d.hint;
          var link = $("#downloadLink");
          link.href = "/api/runs/" + state.runId + "/export?format=" + state.format;
          link.setAttribute("download", d.filename);
        });
    }

    $$("#exportBar .chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        $$("#exportBar .chip").forEach(function (c) { c.classList.remove("on"); });
        chip.classList.add("on");
        state.format = chip.dataset.fmt;
        loadPreview();
      });
    });

    $("#copyBtn").addEventListener("click", function () {
      var text = $("#exportPreview").textContent || "";
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () { toast("已复制"); },
          function () { toast("复制失败，请手动选择"); });
      }
    });

    $("#saveBtn").addEventListener("click", function () {
      if (!state.runId) return;
      if (state.saved) {
        toast("已经收过了");
        return;
      }
      var btn = $("#saveBtn");
      btn.disabled = true;
      btn.textContent = "保存中…";
      fetch("/api/runs/" + state.runId + "/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.detail) { toast(d.detail); btn.disabled = false; btn.textContent = "收进库"; return; }
        state.saved = d;
        btn.textContent = "已收下 v" + d.version;
        var link = $("#libraryLink");
        link.style.display = "";
        toast("已收下 v" + d.version);
      }).catch(function () {
        btn.disabled = false;
        btn.textContent = "收进库";
        toast("保存失败");
      });
    });

    /* ---- 启动 ---- */
    runBtn.addEventListener("click", function () {
      var text = conv.value.trim();
      if (text.length < 20) { toast("对话太短了，至少 20 个字"); return; }

      resetAll();
      runBtn.disabled = true;
      runBtn.textContent = "提炼中…";
      runStatus.textContent = "已提交";

      fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation: text, base_skill_id: baseId || null })
      }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, data: d }; });
      }).then(function (res) {
        if (!res.ok) {
          toast(res.data.detail || "提交失败");
          finishUI();
          return;
        }
        state.runId = res.data.run_id;
        $("#providerHint").textContent = res.data.provider === "llm" ? "模型模式" : "规则引擎 · 本地运行";
        setAct("signals", "running", "进行中");
        subscribe(state.runId);
      }).catch(function () {
        toast("网络错误");
        finishUI();
      });
    });

    // 从 ?sample= 进来时自动填好，但仍需用户点按钮，避免误触发
    if (conv.value.trim()) {
      $$("#sampleChips .chip").forEach(function (c) {
        if (c.dataset.text === conv.value) c.classList.add("on");
      });
    }
  }

  /* ================= Skill 库 ================= */
  function initLibrary() {
    var list = $("#skillList");

    function load() {
      list.innerHTML = '<div class="empty">加载中…</div>';
      fetch("/api/skills").then(function (r) { return r.json(); }).then(function (d) {
        if (!d.items || !d.items.length) {
          list.innerHTML = '<div class="empty">库里还是空的。<br/><a href="/play" style="color:var(--teal)">先跑一段对话 →</a></div>';
          return;
        }
        list.innerHTML = d.items.map(function (s) {
          return '<div class="skill-row">' +
            '<div style="min-width:0">' +
            '<div class="skill-name">' + esc(s.name) + "</div>" +
            '<div class="skill-desc">' + esc(s.description) + "</div>" +
            "</div>" +
            '<div class="skill-side">' +
            '<span class="badge">v' + s.latest_v + "</span>" +
            '<a class="btn btn-sm" href="/api/skills/' + s.id + '/export?format=claude-code">下载 SKILL.md</a>' +
            '<a class="btn btn-sm btn-ghost" href="/play?base=' + s.id + '">接一段新的</a>' +
            '<button class="btn btn-sm btn-ghost" data-del="' + s.id + '">删除</button>' +
            "</div></div>";
        }).join("");

        $$("[data-del]", list).forEach(function (b) {
          b.addEventListener("click", function () {
            if (!confirm("确定删除这个 skill 以及它的所有版本？")) return;
            fetch("/api/skills/" + b.dataset.del, { method: "DELETE" }).then(load);
          });
        });
      }).catch(function () {
        list.innerHTML = '<div class="empty">加载失败</div>';
      });
    }

    var refresh = $("#refreshBtn");
    if (refresh) refresh.addEventListener("click", load);
    load();
  }

  if (document.getElementById("conv")) initPlay();
  if (document.getElementById("skillList")) initLibrary();
})();
