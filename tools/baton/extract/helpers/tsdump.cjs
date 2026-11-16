// Reads file paths on stdin, one per line; writes one JSON object per file: the REST calls found in it.
// argv: repo root, vendored typescript.js. The repo's own TypeScript parses its code if it has the JS API.
"use strict";
const fs = require("fs");

function loadTypescript(repo, vendored) {
  try {
    const ts = require(require.resolve("typescript", { paths: [repo] }));
    if (typeof ts.createSourceFile === "function") return ts;
  } catch (_) {
    // no usable copy in the repo
  }
  return require(vendored);
}

const ts = loadTypescript(process.argv[2], process.argv[3]);
const VERBS = new Set(["get", "post", "put", "delete", "patch", "head", "options"]);

function kindFor(path) {
  if (path.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (path.endsWith(".ts")) return ts.ScriptKind.TS;
  return ts.ScriptKind.JSX;
}

function dump(path) {
  const source = ts.createSourceFile(path, fs.readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true, kindFor(path));
  if (source.parseDiagnostics.length) {
    const first = source.parseDiagnostics[0];
    return { ok: false, reason: ts.flattenDiagnosticMessageText(first.messageText, " ") };
  }
  const constants = new Map();
  const clients = new Map();
  const lineOf = (node) => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;

  function env(node) {
    if (!ts.isPropertyAccessExpression(node)) return null;
    const text = node.expression.getText(source);
    return text === "process.env" || text === "import.meta.env" ? node.name.text : null;
  }

  // text: the URL with {name} for a path variable and ${name} for a value the file cannot tell.
  function url(node) {
    if (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) || ts.isNonNullExpression(node)) {
      return url(node.expression);
    }
    if (ts.isStringLiteralLike(node)) return node.text;
    if (ts.isIdentifier(node)) return constants.has(node.text) ? constants.get(node.text) : null;
    const variable = env(node);
    if (variable) return "${" + variable + "}";
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const left = url(node.left);
      if (left === null) return null;
      return left + part(node.right, left === "");
    }
    if (ts.isTemplateExpression(node)) {
      let out = node.head.text;
      for (const span of node.templateSpans) {
        out += part(span.expression, out === "") + span.literal.text;
      }
      return out;
    }
    return null;
  }

  function part(node, leading) {
    const known = url(node);
    if (known !== null) return known;
    const name = ts.isIdentifier(node) ? node.text : ts.isPropertyAccessExpression(node) ? node.name.text : "value";
    return leading ? "${" + name + "}" : "{" + name + "}";
  }

  function property(object, name) {
    if (!object || !ts.isObjectLiteralExpression(object)) return null;
    for (const item of object.properties) {
      if (ts.isPropertyAssignment(item) && item.name.getText(source).replace(/['"]/g, "") === name) return item.initializer;
    }
    return null;
  }

  function verb(node, fallback) {
    if (!node) return fallback;
    return ts.isStringLiteralLike(node) ? node.text.toUpperCase() : "ANY";
  }

  function collect(node) {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const parent = node.parent.parent;
      const init = node.initializer;
      if (ts.isVariableStatement(parent) && parent.parent === source && node.parent.flags & ts.NodeFlags.Const) {
        const value = url(init);
        if (value !== null) constants.set(node.name.text, value);
      }
      if (ts.isCallExpression(init) && init.expression.getText(source) === "axios.create") {
        const base = property(init.arguments[0], "baseURL");
        clients.set(node.name.text, base ? (url(base) ?? "${" + node.name.text + ".baseURL}") : "");
      }
    }
    ts.forEachChild(node, collect);
  }
  collect(source);

  const calls = [];
  function add(node, extractor, method, target, base) {
    const value = target ? url(target) : null;
    calls.push({ line: lineOf(node), extractor, method, url: value === null ? null : base + value });
  }

  function visit(node) {
    if (ts.isCallExpression(node)) {
      const callee = node.expression.getText(source);
      const [first, second] = node.arguments;
      if (callee === "fetch" || callee === "window.fetch" || callee === "globalThis.fetch") {
        add(node, "ts-fetch", verb(property(second, "method"), "GET"), first, "");
      } else if (callee === "axios" || callee === "axios.request") {
        const config = first && ts.isObjectLiteralExpression(first) ? first : second;
        const target = first && ts.isObjectLiteralExpression(first) ? property(first, "url") : first;
        add(node, "ts-axios", verb(property(config, "method"), "GET"), target, "");
      } else if (ts.isPropertyAccessExpression(node.expression) && VERBS.has(node.expression.name.text)) {
        const owner = node.expression.expression.getText(source);
        if (owner === "axios" || clients.has(owner)) {
          const base = owner === "axios" ? "" : clients.get(owner);
          add(node, "ts-axios", node.expression.name.text.toUpperCase(), first, base);
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
  return { ok: true, calls };
}

console.log(JSON.stringify({ typescript: ts.version }));
for (const path of fs.readFileSync(0, "utf8").split("\n").filter(Boolean)) {
  let result;
  try {
    result = dump(path);
  } catch (error) {
    result = { ok: false, reason: String(error) };
  }
  console.log(JSON.stringify(result));
}
