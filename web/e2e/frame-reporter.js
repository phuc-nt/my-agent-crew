(function () {
  var MAX_MESSAGES = 20;
  var MAX_CHARS = 2000;
  var sent = 0;
  function text(value) {
    return typeof value === "string" ? value : "";
  }
  function number(value) {
    return typeof value === "number" ? value : 0;
  }
  function reason(value) {
    try {
      var shown = String(value);
      if (shown !== "[object Object]") {
        return shown;
      }
      return typeof value.message === "string" ? value.message : JSON.stringify(value);
    } catch (ignored) {
      return "unhandled rejection";
    }
  }
  function report(what, source, line, column) {
    try {
      if (sent >= MAX_MESSAGES) {
        return;
      }
      var message = String(what).slice(0, MAX_CHARS);
      sent += 1;
      parent.postMessage({
        type: "canvas-error",
        message: message,
        source: text(source),
        line: number(line),
        column: number(column)
      }, "*");
    } catch (ignored) {}
  }
  window.addEventListener("error", function (event) {
    try {
      var target = event.target;
      if (target && target.nodeType === 1) {
        var url = text(target.currentSrc) || text(target.src) || text(target.href);
        report("failed to load " + (url || target.tagName.toLowerCase()), url, 0, 0);
      } else {
        report(event.message, event.filename, event.lineno, event.colno);
      }
    } catch (ignored) {}
  }, true);
  window.addEventListener("unhandledrejection", function (event) {
    report(reason(event.reason), "", 0, 0);
  });
  window.addEventListener("securitypolicyviolation", function (event) {
    report(
      (event.effectiveDirective || event.violatedDirective) + " blocked " + event.blockedURI,
      event.sourceFile, event.lineNumber, event.columnNumber
    );
  });
})();
