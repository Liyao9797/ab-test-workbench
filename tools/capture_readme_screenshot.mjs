import { writeFile } from "node:fs/promises";

const chromeJsonUrl = "http://127.0.0.1:9222/json";
const targetUrl = "http://127.0.0.1:5173/";
const outputPath = new URL("../docs/assets/readme/product-workbench.png", import.meta.url);

async function main() {
  const targets = await fetch(chromeJsonUrl).then((response) => response.json());
  const page = targets.find((target) => target.type === "page") ?? targets[0];
  if (!page?.webSocketDebuggerUrl) {
    throw new Error("No Chrome page target found. Start Chrome with --remote-debugging-port=9222 first.");
  }

  const cdp = await connect(page.webSocketDebuggerUrl);
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1680,
    height: 1280,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await cdp.send("Page.navigate", { url: targetUrl });
  await waitFor(cdp, () => document.body.innerText.includes("产品增长实验分析工作台"));
  await clickButton(cdp, "生成 demo");
  await waitFor(cdp, () => document.body.innerText.includes("feature_clicked"));
  await clickButton(cdp, "Step 2 分析 Excel");
  await waitFor(cdp, () => document.body.innerText.includes("PM 结论") || document.body.innerText.includes("PASS_WITH_WARNING"));
  await clickButton(cdp, "Step 3 生成图表");
  await waitFor(cdp, () => document.querySelectorAll(".chart-card img").length >= 1);
  await sleep(800);

  const screenshot = await cdp.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await writeFile(outputPath, Buffer.from(screenshot.data, "base64"));
  console.log(outputPath.pathname);
  cdp.close();
}

async function clickButton(cdp, text) {
  const result = await cdp.send("Runtime.evaluate", {
    awaitPromise: true,
    returnByValue: true,
    expression: `
      (() => {
        const buttons = [...document.querySelectorAll("button")];
        const button = buttons.find((item) => item.innerText.includes(${JSON.stringify(text)}));
        if (!button) return false;
        button.scrollIntoView({ block: "center", inline: "center" });
        button.click();
        return true;
      })()
    `,
  });
  if (!result.result.value) {
    throw new Error(`Button not found: ${text}`);
  }
}

async function waitFor(cdp, predicate, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const result = await cdp.send("Runtime.evaluate", {
      awaitPromise: true,
      returnByValue: true,
      expression: `(${predicate.toString()})()`,
    });
    if (result.result.value) return;
    await sleep(250);
  }
  throw new Error("Timed out waiting for browser state.");
}

function connect(url) {
  const ws = new WebSocket(url);
  let id = 0;
  const pending = new Map();

  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id) return;
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    if (message.error) {
      request.reject(new Error(message.error.message));
    } else {
      request.resolve(message.result ?? {});
    }
  });

  return new Promise((resolve, reject) => {
    ws.addEventListener("open", () => {
      resolve({
        send(method, params = {}) {
          const requestId = ++id;
          ws.send(JSON.stringify({ id: requestId, method, params }));
          return new Promise((requestResolve, requestReject) => {
            pending.set(requestId, { resolve: requestResolve, reject: requestReject });
          });
        },
        close() {
          ws.close();
        },
      });
    });
    ws.addEventListener("error", reject);
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
