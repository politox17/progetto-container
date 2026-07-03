const PRESTITO_API_BASE = "http://localhost:8000";
const MODIFICA_API_BASE = "http://localhost:8001";

async function popolaCatalogo() {
  const lista = document.getElementById("catalogo");
  const select = document.getElementById("libro");
  try {
    const risposta = await fetch(`${PRESTITO_API_BASE}/libri`);
    const libri = await risposta.json();
    lista.innerHTML = "";
    select.innerHTML = "";

    libri.forEach((libro) => {
      const etichetta = `${libro.titolo} - ${libro.autore}`;

      const li = document.createElement("li");
      li.textContent = etichetta;
      lista.appendChild(li);

      const opt = document.createElement("option");
      opt.value = libro.titolo;
      opt.textContent = etichetta;
      select.appendChild(opt);
    });
  } catch (err) {
    lista.innerHTML = `<li>Impossibile caricare il catalogo: ${err.message}</li>`;
  }
}

async function caricaPrestitiModificabili() {
  const tbody = document.getElementById("prestiti-modificabili");
  tbody.innerHTML = `<tr><td colspan="5">Caricamento...</td></tr>`;

  try {
    const risposta = await fetch(`${MODIFICA_API_BASE}/prestiti`);
    const prestiti = await risposta.json();

    if (!prestiti.length) {
      tbody.innerHTML = `<tr><td colspan="5">Nessun prestito sincronizzato.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    prestiti.forEach((prestito) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${prestito.id}</td>
        <td>${prestito.utente}</td>
        <td>${prestito.libro}</td>
        <td>${prestito.scadenza}</td>
        <td><button type="button" data-prestito-id="${prestito.id}" data-scadenza="${prestito.scadenza}">Modifica</button></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5">Errore: ${err.message}</td></tr>`;
  }
}

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
    const risposta = await fetch(`${PRESTITO_API_BASE}/prestiti`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (risposta.status === 201) {
      esito.textContent = `Prestito creato per "${payload.libro}" e pubblicato su RabbitMQ.`;
      esito.classList.add("ok");
      setTimeout(caricaPrestitiModificabili, 700);
    } else {
      esito.textContent = `Risposta inattesa: HTTP ${risposta.status}`;
      esito.classList.add("ko");
    }
  } catch (err) {
    esito.textContent = `Errore di rete: ${err.message}`;
    esito.classList.add("ko");
  }
}

function preparaModifica(prestitoId, scadenza) {
  document.getElementById("prestito-id").value = prestitoId;
  document.getElementById("nuova-scadenza").value = scadenza;
  document.getElementById("esito-modifica").textContent = "";
  document.getElementById("nuova-scadenza").focus();
}

async function inviaModifica(evento) {
  evento.preventDefault();
  const esito = document.getElementById("esito-modifica");
  const prestitoId = document.getElementById("prestito-id").value.trim();
  const scadenza = document.getElementById("nuova-scadenza").value;

  esito.textContent = "Modifica in corso...";
  esito.className = "esito";

  try {
    const risposta = await fetch(`${MODIFICA_API_BASE}/prestiti/${prestitoId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scadenza }),
    });

    if (risposta.ok) {
      esito.textContent = "Scadenza aggiornata e evento pubblicato su RabbitMQ.";
      esito.classList.add("ok");
      await caricaPrestitiModificabili();
    } else {
      const dettaglio = await risposta.json();
      esito.textContent = dettaglio.detail || `Risposta inattesa: HTTP ${risposta.status}`;
      esito.classList.add("ko");
    }
  } catch (err) {
    esito.textContent = `Errore di rete: ${err.message}`;
    esito.classList.add("ko");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  popolaCatalogo();
  caricaPrestitiModificabili();

  document.getElementById("form-prestito").addEventListener("submit", inviaPrestito);
  document.getElementById("form-modifica").addEventListener("submit", inviaModifica);
  document.getElementById("aggiorna-prestiti").addEventListener("click", caricaPrestitiModificabili);

  document.getElementById("prestiti-modificabili").addEventListener("click", (evento) => {
    const bottone = evento.target.closest("button[data-prestito-id]");
    if (!bottone) return;
    preparaModifica(bottone.dataset.prestitoId, bottone.dataset.scadenza);
  });
});
