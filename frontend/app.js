// Frontend libreria — Passo 3.
// Mostra un catalogo statico e invia il form a POST /prestiti dell'API.

// L'API è pubblicata su localhost:8000 (il browser gira sulla macchina host,
const API_BASE = "http://localhost:8000";

// Popola la lista del catalogo e la select del form leggendo dal DB via API.
async function popolaCatalogo() {
  const lista = document.getElementById("catalogo");
  const select = document.getElementById("libro");
  try {
    const risposta = await fetch(`${API_BASE}/libri`);
    const libri = await risposta.json();
    libri.forEach((libro) => {
      const etichetta = `${libro.titolo} — ${libro.autore}`;

      const li = document.createElement("li");
      li.textContent = etichetta;
      lista.appendChild(li);

      // value = solo il titolo, è ciò che l'API si aspetta nel prestito
      const opt = document.createElement("option");
      opt.value = libro.titolo;
      opt.textContent = etichetta;
      select.appendChild(opt);
    });
  } catch (err) {
    lista.innerHTML = `<li>Impossibile caricare il catalogo: ${err.message}</li>`;
  }
}

// Gestione invio form → POST /prestiti.
async function inviaPrestito(evento) {
  evento.preventDefault();
  const esito = document.getElementById("esito");
  esito.textContent = "Invio in corso...";
  esito.className = "esito";

  const payload = {
    utente: document.getElementById("utente").value.trim(),
    libro: document.getElementById("libro").value,
    scadenza: document.getElementById("scadenza").value,
  };

  try {
    const risposta = await fetch(`${API_BASE}/prestiti`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (risposta.status === 201) {
      esito.textContent = `Prestito creato per "${payload.libro}" (notifica in coda).`;
      esito.classList.add("ok");
    } else {
      esito.textContent = `Risposta inattesa: HTTP ${risposta.status}`;
      esito.classList.add("ko");
    }
  } catch (err) {
    esito.textContent = `Errore di rete: ${err.message}`;
    esito.classList.add("ko");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  popolaCatalogo();
  document
    .getElementById("form-prestito")
    .addEventListener("submit", inviaPrestito);
});
