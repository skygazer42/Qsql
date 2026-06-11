// [CUSTOM] 给 SQL 训练弹窗补充“问题”输入框，并随 /api/v0/train 一起提交。
// 当前仓库只保留了打包后的前端产物，因此这里用轻量补丁避免直接修改压缩后的 bundle。
(function () {
  const QUESTION_FIELD_ID = "custom-training-question";
  const QUESTION_WRAPPER_ID = "custom-training-question-wrapper";

  const originalFetch = window.fetch.bind(window);

  function isTrainUrl(input) {
    const url = typeof input === "string" ? input : input && input.url;
    return typeof url === "string" && url.includes("/api/v0/train");
  }

  function rewritePlotlyFigureUrl(input) {
    const url = typeof input === "string" ? input : input && input.url;
    const route = "/api/v0/generate_plotly_figure";

    if (
      typeof url !== "string" ||
      !url.includes(route) ||
      url.includes(`${route}/json`)
    ) {
      return input;
    }

    // [CUSTOM] 当前打包前端调用无 /json 图表接口；兼容旧后端进程只注册 /json 的情况。
    const rewrittenUrl = url.replace(route, `${route}/json`);
    if (typeof input === "string") {
      return rewrittenUrl;
    }

    try {
      return new Request(rewrittenUrl, input);
    } catch (error) {
      return input;
    }
  }

  function getQuestionValue() {
    const field = document.getElementById(QUESTION_FIELD_ID);
    return field ? field.value.trim() : "";
  }

  window.fetch = function (input, init) {
    input = rewritePlotlyFigureUrl(input);

    if (isTrainUrl(input) && init && init.method === "POST" && init.body) {
      try {
        const payload = JSON.parse(init.body);
        const question = getQuestionValue();

        // 只增强 SQL 训练：DDL / Documentation 不应该带 question。
        if (payload && payload.sql && question && !payload.question) {
          init = {
            ...init,
            body: JSON.stringify({ ...payload, question }),
          };
        }
      } catch (error) {
        // 非 JSON 请求保持原样，避免影响其它接口。
      }
    }

    return originalFetch(input, init);
  };

  function isSqlTrainingSelected() {
    const sqlRadio = document.getElementById("hs-radio-SQL");
    return Boolean(sqlRadio && sqlRadio.checked);
  }

  function findTrainingTextarea() {
    return document.getElementById("hs-feedback-post-comment-textarea-1");
  }

  function removeQuestionField() {
    const wrapper = document.getElementById(QUESTION_WRAPPER_ID);
    if (wrapper) {
      wrapper.remove();
    }
  }

  function ensureQuestionField() {
    const textarea = findTrainingTextarea();
    if (!textarea) {
      removeQuestionField();
      return;
    }

    const label = textarea.parentElement && textarea.parentElement.previousElementSibling;
    const isSqlLabel = label && label.textContent.trim() === "Your SQL";

    if (!isSqlTrainingSelected() || !isSqlLabel) {
      removeQuestionField();
      return;
    }

    if (document.getElementById(QUESTION_WRAPPER_ID)) {
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.id = QUESTION_WRAPPER_ID;
    wrapper.className = "mb-4";
    wrapper.innerHTML = `
      <label for="${QUESTION_FIELD_ID}" class="block mt-2 mb-2 text-sm font-medium dark:text-white">
        Your Question
      </label>
      <input
        id="${QUESTION_FIELD_ID}"
        name="question"
        type="text"
        class="py-3 px-4 block w-full border-gray-200 rounded-md text-sm focus:border-blue-500 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-400"
        placeholder="例如：查询风险扫描列表"
      />
      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
        可选；填写后会把该问题和 SQL 作为成对训练数据保存。
      </p>
    `;

    label.parentElement.insertBefore(wrapper, label);
  }

  function scheduleEnsureQuestionField() {
    window.requestAnimationFrame(ensureQuestionField);
  }

  document.addEventListener("change", scheduleEnsureQuestionField, true);
  document.addEventListener("click", scheduleEnsureQuestionField, true);

  const observer = new MutationObserver(scheduleEnsureQuestionField);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  scheduleEnsureQuestionField();
})();
