(() => {
  if (window.__ppchatMoodleExport) return window.__ppchatMoodleExport.focus();

  const panel = document.createElement("div");
  panel.innerHTML = `
    <style>
      #ppx-moodle{position:fixed;top:16px;right:16px;z-index:2147483647;width:360px;max-width:calc(100vw - 32px);
        font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:#191b18;background:#fff;border-radius:16px;
        box-shadow:0 24px 60px -12px rgba(0,0,0,.45);border:1px solid #e5e2da;overflow:hidden}
      #ppx-moodle header{display:flex;align-items:center;gap:10px;padding:14px 16px;background:#1f8a4c;color:#fff}
      #ppx-moodle header b{font-size:15px}#ppx-moodle header button{margin-left:auto;background:none;border:0;color:#fff;font-size:20px;cursor:pointer}
      #ppx-moodle .body{padding:14px 16px}#ppx-moodle ul{margin:8px 0;padding:0;list-style:none;max-height:220px;overflow:auto}
      #ppx-moodle li{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-bottom:1px solid #f0eee8;font-size:13px}
      #ppx-moodle li span:last-child{color:#6c7068;white-space:nowrap}#ppx-moodle .muted{color:#6c7068;font-size:12.5px}
      #ppx-moodle .err{color:#b3261e}#ppx-moodle .btn{display:block;width:100%;margin-top:12px;padding:10px;border:0;border-radius:10px;
        background:#1f8a4c;color:#fff;font-weight:600;font-size:14px;cursor:pointer;text-align:center;text-decoration:none;box-sizing:border-box}
      #ppx-moodle .btn[disabled]{opacity:.5;cursor:default}#ppx-moodle .ghost{background:#f3f1ec;color:#191b18}
    </style>
    <div id="ppx-moodle" role="dialog" aria-label="Enviar dados do Moodle para o PPChat">
      <header><b>PPChat ← Moodle</b><button type="button" data-close aria-label="Fechar">×</button></header>
      <div class="body"><div data-status>Lendo suas atividades do Moodle…</div><ul data-list></ul><div data-actions></div></div>
    </div>`;
  document.body.append(panel);

  const $ = (sel) => panel.querySelector(sel);
  const close = () => { panel.remove(); delete window.__ppchatMoodleExport; };
  $("[data-close]").addEventListener("click", close);
  window.__ppchatMoodleExport = { focus: () => panel.scrollIntoView() };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const status = (html) => ($("[data-status]").innerHTML = html);

  if (!location.hostname.includes("moodle")) {
    status(`<span class="err">Abra <b>moodle.scl.ifsp.edu.br/my/</b> e clique neste favorito novamente.</span>`);
    return;
  }

  const tasks = [];
  document.querySelectorAll("[data-region='event-list-item'], .event, .calendar_event_course, .list-group-item").forEach((el) => {
    const titleEl = el.querySelector("a, h6, .event-name, .name");
    const title = titleEl?.textContent?.trim();
    if (!title || title.length < 3) return;
    const course = el.querySelector(".course-name, small, .text-muted")?.textContent?.trim() || null;
    const due = el.querySelector("time, .date, [data-region='event-time']")?.textContent?.trim() || null;
    const url = titleEl?.href || null;
    if (!tasks.some((t) => t.title === title && t.due === due)) {
      tasks.push({ title: title.slice(0, 300), course: course?.slice(0, 200) || null, due: due?.slice(0, 120) || null, url });
    }
  });

  if (!tasks.length) {
    status(`<span class="err">Nenhuma atividade encontrada nesta página.</span><div class="muted">Certifique-se de estar no Painel (/my/) com a Linha do tempo visível.</div>`);
    return;
  }

  status(`<b>${tasks.length} atividade(s)</b> encontrada(s). Isto é o que será enviado ao PPChat:<div class="muted">As tarefas serão exibidas na aba Moodle e enviadas ao WhatsApp (se configurado).</div>`);
  $("[data-list]").innerHTML = tasks.slice(0, 12).map((t) =>
    `<li><span>${esc(t.title)}</span><span>${esc(t.due || t.course || "Moodle")}</span></li>`
  ).join("") + (tasks.length > 12 ? `<li><span class="muted">+ ${tasks.length - 12} mais…</span><span></span></li>` : "");

  const api = window.__PPCHAT_API || "http://127.0.0.1:8000";
  $("[data-actions]").innerHTML = `<button class="btn" data-send>Enviar e abrir o PPChat</button>`;
  $("[data-send]").addEventListener("click", async (event) => {
    event.target.disabled = true;
    event.target.textContent = "Enviando…";
    try {
      const res = await fetch(`${api}/moodle/importar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tasks, notify_whatsapp: true }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Falha ao enviar");
      const url = `${api}/#moodle=${d.token}`;
      $("[data-actions]").innerHTML = `<a class="btn" href="${esc(url)}" target="_blank" rel="noopener">Abrir no PPChat</a><button class="btn ghost" data-close2>Fechar</button>`;
      $("[data-close2]").addEventListener("click", close);
      window.open(url, "_blank", "noopener");
    } catch (e) {
      status(`<span class="err">Erro ao enviar para o PPChat: ${esc(e.message)}</span>`);
      event.target.disabled = false;
      event.target.textContent = "Tentar novamente";
    }
  });
})();
