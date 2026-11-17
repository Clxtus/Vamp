const vscode = require("vscode");
const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");

const KEYWORDS = [
  "import", "from", "as", "val", "const", "func", "return", "if", "else", "for", "in", "while", "class", "struct",
  "enum", "interface", "match", "break", "continue", "try", "catch", "throw", "test", "and", "or", "not", "none",
  "true", "false", "self", "super",
];
const TYPES = [
  "int", "float", "bool", "str", "char", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "double",
  "list", "map", "set", "json", "builder", "void",
];
const BUILTINS = ["print", "println", "len", "range", "exit", "free", "malloc", "assert", "builder"];

// repo checkout (Compiler/main.py) > installed vamp.exe > vamp on PATH
function compilerCommand(document) {
  const configured = vscode.workspace.getConfiguration("vamp").get("compiler");
  if (configured) {
    const parts = configured.match(/(?:[^\s"]+|"[^"]*")+/g).map((part) => part.replace(/^"|"$/g, ""));
    return { command: parts[0], prefix: parts.slice(1) };
  }
  const folder = vscode.workspace.getWorkspaceFolder(document.uri);
  if (folder) {
    const script = path.join(folder.uri.fsPath, "Compiler", "main.py");
    if (fs.existsSync(script)) {
      return { command: "python", prefix: [script] };
    }
  }
  const installed = path.join(process.env.LOCALAPPDATA || "", "Programs", "Vamp", "vamp.exe");
  if (process.env.LOCALAPPDATA && fs.existsSync(installed)) {
    return { command: installed, prefix: [] };
  }
  return { command: "vamp", prefix: [] };
}

function runCompiler(document, args, input) {
  const { command, prefix } = compilerCommand(document);
  return new Promise((resolve) => {
    const child = childProcess.execFile(
      command,
      [...prefix, ...args],
      { cwd: path.dirname(document.uri.fsPath), maxBuffer: 32 * 1024 * 1024, windowsHide: true },
      (error, stdout, stderr) => resolve({ error, stdout, stderr })
    );
    if (input !== undefined) {
      child.stdin.end(input, "utf8");
    }
  });
}

const symbolCache = new Map();

async function symbolsFor(document) {
  const key = document.uri.toString();
  const cached = symbolCache.get(key);
  if (cached && cached.version === document.version) {
    return cached.data;
  }
  const result = await runCompiler(document, ["symbols", document.uri.fsPath]);
  let data = { symbols: [], libraries: {} };
  try {
    data = JSON.parse(result.stdout);
  } catch (ignored) {
    data = cached ? cached.data : data;
  }
  symbolCache.set(key, { version: document.version, data });
  return data;
}

function wordAt(document, position) {
  const range = document.getWordRangeAtPosition(position, /[A-Za-z_][A-Za-z0-9_]*/);
  if (!range) {
    return null;
  }
  const word = document.getText(range);
  const before = document.lineAt(position.line).text.slice(0, range.start.character);
  const owner = before.match(/([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*$/);
  return { word, range, owner: owner ? owner[1] : null };
}

function bestSymbol(symbols, word, document, line) {
  const matches = symbols.filter((symbol) => symbol.name === word);
  if (matches.length === 0) {
    return null;
  }
  const here = matches.filter((symbol) => symbol.file && path.resolve(symbol.file) === path.resolve(document.uri.fsPath));
  const pool = here.length ? here : matches;
  const before = pool.filter((symbol) => symbol.line - 1 <= line).sort((a, b) => b.line - a.line);
  return before[0] || pool[0];
}

function activate(context) {
  const diagnostics = vscode.languages.createDiagnosticCollection("vamp");
  context.subscriptions.push(diagnostics);

  async function check(document) {
    if (document.languageId !== "vamp" || document.uri.scheme !== "file") {
      return;
    }
    const result = await runCompiler(document, ["check", document.uri.fsPath, "--json"]);
    let problems = [];
    try {
      problems = JSON.parse(result.stdout);
    } catch (ignored) {
      if (result.error && result.error.code === "ENOENT") {
        vscode.window.showWarningMessage("Vamp: could not start the compiler. Set 'vamp.compiler' in the settings.");
      }
      return;
    }
    const byFile = new Map();
    for (const problem of problems) {
      const file = problem.file ? path.resolve(problem.file) : document.uri.fsPath;
      const start = new vscode.Position(Math.max(problem.line - 1, 0), Math.max(problem.column - 1, 0));
      const range = new vscode.Range(start, start.translate(0, Math.max(problem.width || 1, 1)));
      const message = problem.hint ? `${problem.message}\nhint: ${problem.hint}` : problem.message;
      const item = new vscode.Diagnostic(range, message, vscode.DiagnosticSeverity.Error);
      item.source = "vamp";
      if (!byFile.has(file)) {
        byFile.set(file, []);
      }
      byFile.get(file).push(item);
    }
    diagnostics.delete(document.uri);
    if (!byFile.has(path.resolve(document.uri.fsPath))) {
      diagnostics.set(document.uri, []);
    }
    for (const [file, items] of byFile) {
      diagnostics.set(vscode.Uri.file(file), items);
    }
  }

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(check),
    vscode.workspace.onDidOpenTextDocument(check),
    vscode.workspace.onDidCloseTextDocument((document) => diagnostics.delete(document.uri))
  );
  vscode.workspace.textDocuments.forEach(check);

  context.subscriptions.push(vscode.languages.registerHoverProvider("vamp", {
    async provideHover(document, position) {
      const target = wordAt(document, position);
      if (!target) {
        return null;
      }
      const data = await symbolsFor(document);
      if (target.owner && data.libraries[target.owner]) {
        const entry = data.libraries[target.owner].find((item) => item.name === target.word);
        if (entry) {
          return new vscode.Hover(new vscode.MarkdownString().appendCodeblock(`${target.owner}.${entry.detail}`, "vamp"));
        }
      }
      const symbol = bestSymbol(data.symbols, target.word, document, position.line);
      if (!symbol) {
        return null;
      }
      const owner = symbol.container ? `(${symbol.kind} in ${symbol.container})` : `(${symbol.kind})`;
      return new vscode.Hover(new vscode.MarkdownString().appendCodeblock(symbol.detail, "vamp").appendText(owner));
    },
  }));

  context.subscriptions.push(vscode.languages.registerDefinitionProvider("vamp", {
    async provideDefinition(document, position) {
      const target = wordAt(document, position);
      if (!target) {
        return null;
      }
      const data = await symbolsFor(document);
      const symbol = bestSymbol(data.symbols, target.word, document, position.line);
      if (!symbol || !symbol.line) {
        return null;
      }
      const file = symbol.file ? vscode.Uri.file(symbol.file) : document.uri;
      return new vscode.Location(file, new vscode.Position(symbol.line - 1, Math.max(symbol.column - 1, 0)));
    },
  }));

  context.subscriptions.push(vscode.languages.registerCompletionItemProvider("vamp", {
    async provideCompletionItems(document, position) {
      const data = await symbolsFor(document);
      const before = document.lineAt(position.line).text.slice(0, position.character);
      const member = before.match(/([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*[A-Za-z0-9_]*$/);
      if (member && data.libraries[member[1]]) {
        return data.libraries[member[1]].map((entry) => {
          const item = new vscode.CompletionItem(entry.name, vscode.CompletionItemKind.Function);
          item.detail = entry.detail;
          return item;
        });
      }
      const items = [];
      const seen = new Set();
      const kinds = {
        function: vscode.CompletionItemKind.Function, method: vscode.CompletionItemKind.Method,
        class: vscode.CompletionItemKind.Class, struct: vscode.CompletionItemKind.Struct,
        enum: vscode.CompletionItemKind.Enum, interface: vscode.CompletionItemKind.Interface,
        field: vscode.CompletionItemKind.Field, variable: vscode.CompletionItemKind.Variable,
        parameter: vscode.CompletionItemKind.Variable, enum_member: vscode.CompletionItemKind.EnumMember,
      };
      for (const symbol of data.symbols) {
        if (seen.has(symbol.name) || symbol.kind === "test") {
          continue;
        }
        seen.add(symbol.name);
        const item = new vscode.CompletionItem(symbol.name, kinds[symbol.kind] || vscode.CompletionItemKind.Text);
        item.detail = symbol.detail;
        items.push(item);
      }
      for (const word of KEYWORDS) {
        items.push(new vscode.CompletionItem(word, vscode.CompletionItemKind.Keyword));
      }
      for (const word of TYPES) {
        items.push(new vscode.CompletionItem(word, vscode.CompletionItemKind.TypeParameter));
      }
      for (const word of BUILTINS) {
        items.push(new vscode.CompletionItem(word, vscode.CompletionItemKind.Function));
      }
      for (const library of Object.keys(data.libraries)) {
        items.push(new vscode.CompletionItem(library, vscode.CompletionItemKind.Module));
      }
      return items;
    },
  }, "."));

  context.subscriptions.push(vscode.languages.registerDocumentFormattingEditProvider("vamp", {
    async provideDocumentFormattingEdits(document) {
      const result = await runCompiler(document, ["format", "-"], document.getText());
      if (result.error || !result.stdout) {
        return [];
      }
      const eol = document.eol === vscode.EndOfLine.CRLF ? "\r\n" : "\n";
      const formatted = result.stdout.replace(/\r?\n/g, eol);
      const whole = new vscode.Range(document.positionAt(0), document.positionAt(document.getText().length));
      return [vscode.TextEdit.replace(whole, formatted)];
    },
  }));

  function runInTerminal(args) {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "vamp") {
      vscode.window.showInformationMessage("Open a .vp file first.");
      return;
    }
    editor.document.save().then(() => {
      const { command, prefix } = compilerCommand(editor.document);
      const quoted = [command, ...prefix, ...args(editor.document.uri.fsPath)].map((part) =>
        /[\s']/.test(part) ? `"${part}"` : part);
      let terminal = vscode.window.terminals.find((item) => item.name === "Vamp");
      if (!terminal) {
        terminal = vscode.window.createTerminal({
          name: "Vamp", cwd: path.dirname(editor.document.uri.fsPath), shellPath: "powershell.exe",
        });
      }
      terminal.show();
      terminal.sendText(`& ${quoted.join(" ")}`);
    });
  }

  context.subscriptions.push(
    vscode.commands.registerCommand("vamp.run", () => runInTerminal((file) => ["run", file])),
    vscode.commands.registerCommand("vamp.test", () => runInTerminal((file) => ["test", file])),
    vscode.commands.registerCommand("vamp.buildDebug", () => runInTerminal((file) => [file, "--debug"]))
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
