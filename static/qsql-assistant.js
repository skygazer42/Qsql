(function () {
  const state = {
    datasets: [],
    selectedDataset: "",
    history: [],
    apiKey: window.localStorage.getItem("qsql-api-key") || "",
    busy: false,
  };

  const datasetSelect = document.getElementById("datasetSelect");
  const datasetMeta = document.getElementById("datasetMeta");
  const semanticScope = document.getElementById("semanticScope");
  const serviceStatus = document.getElementById("serviceStatus");
  const datasetCount = document.getElementById("datasetCount");
  const relationshipCount = document.getElementById("relationshipCount");
  const metricCount = document.getElementById("metricCount");
  const examples = document.getElementById("examples");
  const questionInput = document.getElementById("questionInput");
  const askButton = document.getElementById("askButton");
  const clearButton = document.getElementById("clearButton");
  const sqlOutput = document.getElementById("sqlOutput");
  const timingStrip = document.getElementById("timingStrip");
  const answerSummary = document.getElementById("answerSummary");
  const resultTable = document.getElementById("resultTable");
  const apiKeyInput = document.getElementById("apiKeyInput");
  const saveApiKeyButton = document.getElementById("saveApiKeyButton");
  const dockDataset = document.getElementById("dockDataset");
  const chatLog = document.getElementById("chatLog");
  const dockForm = document.getElementById("dockForm");
  const dockInput = document.getElementById("dockInput");

  const examplesByDataset = {
    bird_financial: [
      "按客户区域统计 1998 年贷款金额合计",
      "1998 年 north Bohemia 各交易类型的交易金额",
      "1998 年女性客户且区域为 north Bohemia 的银行卡数按卡类型统计",
    ],
    bird_student_club: [
      "Women's Soccer 活动按专业统计出勤人数",
      "October Meeting 已批准费用按费用说明统计",
      "按活动类型统计 2019 年收入合计",
    ],
    bird_debit_card_specializing: [
      "按加油站国家统计 2012 年交易总花费",
      "按商品描述统计交易数量",
      "按客户分群统计总消费",
    ],
    online_retail: [
      "按国家统计 2011 年销售额",
      "按商品统计 2011 年销售数量",
      "2011 年每月发票数趋势",
    ],
  };

  function setStatus(text, kind) {
    serviceStatus.textContent = text;
    serviceStatus.className = `status-pill${kind ? ` ${kind}` : ""}`;
  }

  function apiHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (state.apiKey) headers["X-API-KEY"] = state.apiKey;
    return headers;
  }

  async function apiFetch(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        ...apiHeaders(),
        ...(options.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.message || payload.error || payload.msg || `${response.status} ${response.statusText}`);
    }
    return payload;
  }

  function formatInt(value) {
    return Number(value || 0).toLocaleString("zh-CN");
  }

  function activeDataset() {
    return state.datasets.find((item) => item.dataset_id === state.selectedDataset) || null;
  }

  function renderDatasetOptions() {
    datasetSelect.innerHTML = state.datasets
      .filter((item) => item.valid !== false)
      .map((item) => `<option value="${item.dataset_id}">${item.dataset_id}</option>`)
      .join("");
    if (!state.selectedDataset && datasetSelect.options.length > 0) {
      const preferred = state.datasets.find((item) => item.dataset_id === "bird_financial");
      state.selectedDataset = preferred ? preferred.dataset_id : datasetSelect.options[0].value;
    }
    datasetSelect.value = state.selectedDataset;
    renderDatasetMeta();
  }

  function renderDatasetMeta() {
    const dataset = activeDataset();
    if (!dataset) {
      datasetMeta.textContent = "未发现可用数据集。";
      semanticScope.innerHTML = "";
      dockDataset.textContent = "未选择";
      return;
    }

    const totals = state.datasets.reduce(
      (acc, item) => {
        acc.relationships += Number(item.relationship_count || 0);
        acc.metrics += Number(item.metric_count || 0);
        return acc;
      },
      { relationships: 0, metrics: 0 }
    );
    datasetCount.textContent = formatInt(state.datasets.length);
    relationshipCount.textContent = formatInt(totals.relationships);
    metricCount.textContent = formatInt(totals.metrics);

    datasetMeta.innerHTML = [
      `版本：${dataset.catalog_version || "-"}`,
      `表 ${formatInt(dataset.table_count)} 张`,
      `指标 ${formatInt(dataset.metric_count)} 个`,
      `维度 ${formatInt(dataset.dimension_count)} 个`,
      `关系 ${formatInt(dataset.relationship_count)} 条`,
    ].join("<br>");
    dockDataset.textContent = dataset.dataset_id;

    const metricRows = (dataset.sample_metrics || [])
      .map((item) => `<div class="scope-row">指标：${item.label} <small>${item.key}</small></div>`)
      .join("");
    const dimensionRows = (dataset.sample_dimensions || [])
      .slice(0, 4)
      .map((item) => `<div class="scope-row">维度：${item.label} <small>${item.key}</small></div>`)
      .join("");
    semanticScope.innerHTML = metricRows + dimensionRows || '<div class="scope-row">暂无摘要。</div>';
    renderExamples();
  }

  function renderExamples() {
    const list = examplesByDataset[state.selectedDataset] || [
      "按主要维度统计核心指标",
      "最近一年核心指标趋势",
      "按分类维度查看指标排名",
    ];
    examples.innerHTML = list
      .map((item) => `<button class="example-chip" type="button" data-question="${encodeURIComponent(item)}">${item}</button>`)
      .join("");
  }

  function appendMessage(role, text) {
    const node = document.createElement("div");
    node.className = `message ${role}`;
    node.textContent = text;
    chatLog.appendChild(node);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function setBusy(busy) {
    state.busy = busy;
    askButton.disabled = busy;
    askButton.textContent = busy ? "正在查询..." : "生成 SQL 并查询";
  }

  function renderTimings(timings) {
    const entries = [
      ["目录", timings.catalog_load_ms],
      ["语义", timings.semantic_agent_ms],
      ["SQL", timings.sql_build_ms],
      ["总计", timings.total_ms],
    ];
    timingStrip.innerHTML = entries
      .map(([label, value]) => `<span>${label} ${formatInt(value)} ms</span>`)
      .join("");
  }

  function renderResultTable(columns, rows) {
    const thead = resultTable.querySelector("thead");
    const tbody = resultTable.querySelector("tbody");
    if (!columns.length) {
      thead.innerHTML = "";
      tbody.innerHTML = '<tr><td>暂无结果。</td></tr>';
      return;
    }

    thead.innerHTML = `<tr>${columns.map((name) => `<th>${name}</th>`).join("")}</tr>`;
    tbody.innerHTML = rows
      .slice(0, 100)
      .map(
        (row) =>
          `<tr>${columns
            .map((column) => {
              const value = row[column];
              return `<td>${value === null || value === undefined ? "" : String(value)}</td>`;
            })
            .join("")}</tr>`
      )
      .join("");
  }

  async function submitQuestion(question) {
    const text = (question || questionInput.value || "").trim();
    if (!text || state.busy) return;
    if (!state.selectedDataset) {
      answerSummary.textContent = "请先选择数据集。";
      return;
    }

    questionInput.value = text;
    dockInput.value = "";
    appendMessage("user", text);
    setBusy(true);
    answerSummary.textContent = "正在解析问题、构造 SQL 并执行只读查询...";
    sqlOutput.textContent = "生成中...";
    timingStrip.innerHTML = "";
    renderResultTable([], []);

    try {
      const payload = await apiFetch("/api/v0/qsql/ask", {
        method: "POST",
        body: JSON.stringify({
          dataset_id: state.selectedDataset,
          question: text,
          history: state.history.slice(-6),
        }),
      });
      state.history.push(text);
      sqlOutput.textContent = payload.sql || "未返回 SQL";
      answerSummary.textContent = payload.message || `返回 ${formatInt(payload.row_count)} 行结果。`;
      renderTimings(payload.timings || {});
      renderResultTable(payload.columns || [], payload.rows || []);
      appendMessage("assistant", `${payload.message || "查询完成"} SQL 已展示在主工作区。`);
      setStatus("服务正常", "ok");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      answerSummary.textContent = message;
      sqlOutput.textContent = "未生成 SQL";
      appendMessage("assistant", message);
      setStatus("请求失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function loadDatasets() {
    try {
      const payload = await apiFetch("/api/v0/qsql/datasets", { method: "GET" });
      state.datasets = payload.datasets || [];
      renderDatasetOptions();
      setStatus("服务正常", "ok");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      datasetMeta.textContent = message;
      setStatus("连接失败", "error");
    }
  }

  datasetSelect.addEventListener("change", () => {
    state.selectedDataset = datasetSelect.value;
    renderDatasetMeta();
  });

  examples.addEventListener("click", (event) => {
    const target = event.target.closest(".example-chip");
    if (!target) return;
    questionInput.value = decodeURIComponent(target.dataset.question || "");
    questionInput.focus();
  });

  askButton.addEventListener("click", () => submitQuestion());
  clearButton.addEventListener("click", () => {
    questionInput.value = "";
    sqlOutput.textContent = "等待问题输入...";
    answerSummary.textContent = "结果会显示在这里。";
    timingStrip.innerHTML = "";
    renderResultTable([], []);
  });

  dockForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitQuestion(dockInput.value);
  });

  apiKeyInput.value = state.apiKey;
  saveApiKeyButton.addEventListener("click", () => {
    state.apiKey = apiKeyInput.value.trim();
    window.localStorage.setItem("qsql-api-key", state.apiKey);
    loadDatasets();
  });

  appendMessage("assistant", "选择数据集后输入问题，我会返回受控 SQL、结果表和耗时。");
  renderResultTable([], []);
  loadDatasets();
})();
