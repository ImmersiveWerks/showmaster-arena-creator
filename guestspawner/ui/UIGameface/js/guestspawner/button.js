// Mod_GuestSpawner: a button in the park HUD that brings 500 more guests.
import * as Engine from "/js/common/core/Engine.js";

const css = (el, s) => { el.style.cssText = s; return el; };
const root = css(document.createElement("div"),
    "position:absolute; left:0.5rem; top:12.5rem; pointer-events:auto; display:flex; flex-direction:column;"
    + "align-items:flex-start; font-size:0.7rem; color:#e6e9ef;");
const btn = css(document.createElement("div"),
    "padding:0.3rem 0.6rem; border-radius:0.35rem; background-color:#2f7de1; color:#ffffff; font-weight:bold;"
    + "cursor:pointer; pointer-events:auto; box-shadow:0 0.1rem 0.3rem rgba(0,0,0,0.4);");
btn.textContent = "+500 Gäste";
const status = css(document.createElement("div"),
    "margin-top:0.2rem; padding:0.1rem 0.4rem; border-radius:0.25rem; background-color:rgba(30,34,40,0.8);"
    + "display:none; white-space:nowrap;");
root.appendChild(btn);
root.appendChild(status);

btn.addEventListener("mousedown", () => { btn.style.backgroundColor = "#1f5fb3"; });
btn.addEventListener("mouseup", () => { btn.style.backgroundColor = "#2f7de1"; });
btn.addEventListener("click", () => {
    try { Engine.sendEvent("GS_Spawn500"); } catch (e) {}
    status.style.display = "block";
    status.textContent = "Gäste kommen ...";
});

Engine.addListener("GS_State", (txt) => {
    if (!txt) { status.style.display = "none"; return; }
    status.style.display = "block";
    if (txt.indexOf("done:") === 0) {
        status.textContent = "Fertig: " + txt.substring(5) + " Gäste im Park";
        setTimeout(() => { status.style.display = "none"; }, 8000);
    } else {
        const parts = txt.split("/");
        status.textContent = "Gäste: " + parts[0] + " / " + parts[1];
    }
});

function mount() {
    if (document.body) {
        document.body.appendChild(root);
        try { Engine.sendEvent("GS_Hello"); } catch (e) {}
    } else {
        setTimeout(mount, 500);
    }
}
mount();
