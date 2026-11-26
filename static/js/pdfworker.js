import * as pdfjsLib from "/pdfjs/pdf.mjs";

const SRC = "/pdfjs/pdf.worker.mjs";
pdfjsLib.GlobalWorkerOptions.workerSrc = SRC;

// PDF を読む作業役（ワーカー）を、画面全体で1つだけ作って使い回す。
// PDF.js に任せると、PDF を読むたびに作業役を作り直す。そのとき pdf.worker.mjs の受け取りが1回でも失敗すると、
// 「Setting up fake worker failed」になり、画面を開き直すまで、まだ読んでいない PDF がすべて表示できなくなる。
// ここで作った作業役が読み込めなかったときは、次に PDF を読むときに作り直す。
// 読み込めなかったことは pw.failed で分かる（読み込み中の PDF を、時間切れまで待たせずに失敗にするため）。
let shared = null;

export function pdfWorker() {
  if (!shared) {
    const w = new Worker(SRC, { type: "module" });
    const pw = pdfjsLib.PDFWorker.fromPort({ port: w });
    let fail;
    pw.failed = new Promise((_, reject) => (fail = reject));
    pw.failed.catch(() => {}); // 待っている PDF が無くても、エラーとして騒がない
    const onError = () => {
      if (shared === pw) shared = null;
      fail(new Error("PDF を読む作業役（pdf.worker.mjs）をサーバーから受け取れませんでした"));
      pw.destroy();
      w.terminate();
    };
    w.addEventListener("error", onError);
    // 作業役が動き出したら（最初の知らせが届いたら）、もう作り直さない
    w.addEventListener("message", () => w.removeEventListener("error", onError), { once: true });
    shared = pw;
  }
  return shared;
}
