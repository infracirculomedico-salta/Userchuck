/**
 * PORTAL WHATSAPP - CÍRCULO MÉDICO DE SALTA
 * Aplicación Single Page Application (SPA) para Gestión de Comunicaciones
 */

// Estado Global de la Aplicación
const AppState = {
  usuario: null,
  activeTab: 'dashboard',
  metricas: null,
  plantillas: [],
  plantillaSeleccionada: null,
  archivosCsv: [],
  archivoCsvSeleccionado: null,
  campanas: [],
  usuarios: [],
  conversaciones: [],
  conversacionActiva: null,
  filtroChat: 'todos',
  mensajeCitar: null,
  modoEnvioChat: 'texto',
  wizard: {
    paso: 1,
    plantilla: null,
    archivoCsv: null,
    mapeoColumnas: {},
    valoresFijos: {},
    simulacion: null,
  },
};

// =====================================================================
// INICIALIZACIÓN
// =====================================================================

document.addEventListener('DOMContentLoaded', async () => {
  inicializarTema();
  configurarEventosNavegacion();
  configurarModales();

  // Verificar sesión activa
  const sesionOk = await verificarSesion();
  if (!sesionOk) {
    window.location.href = '/login';
    return;
  }

  // Cargar datos iniciales
  await Promise.all([
    cargarDashboard(),
    cargarPlantillas(),
    cargarArchivosContactos(),
    actualizarContadorPendientes(),
  ]);
});

// =====================================================================
// CONTROL DE TEMA Y SESIÓN
// =====================================================================

function inicializarTema() {
  const temaGuardado = localStorage.getItem('cirmedsa_theme') || 'light';
  document.documentElement.setAttribute('data-theme', temaGuardado);
  actualizarIconoTema(temaGuardado);

  const btnTema = document.getElementById('btn-toggle-theme');
  if (btnTema) {
    btnTema.addEventListener('click', () => {
      const actual = document.documentElement.getAttribute('data-theme');
      const nuevo = actual === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', nuevo);
      localStorage.setItem('cirmedsa_theme', nuevo);
      actualizarIconoTema(nuevo);
    });
  }
}

function actualizarIconoTema(tema) {
  const icono = document.getElementById('theme-icon');
  if (icono) {
    icono.className = tema === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
  }
}

async function verificarSesion() {
  try {
    const res = await fetch('/api/auth/me');
    if (res.ok) {
      AppState.usuario = await res.json();
      actualizarUIUsuario(AppState.usuario);
      return true;
    }
  } catch (e) {
    console.error('Error verificando sesión:', e);
  }
  return false;
}

function actualizarUIUsuario(user) {
  const elNombre = document.getElementById('user-display-name');
  const elRol = document.getElementById('user-display-role');
  const elAvatar = document.getElementById('user-avatar-initials');

  if (elNombre) elNombre.textContent = user.nombre;
  if (elRol) elRol.textContent = user.rol;
  if (elAvatar) {
    const iniciales = user.nombre
      .split(' ')
      .map((p) => p[0])
      .slice(0, 2)
      .join('');
    elAvatar.textContent = iniciales.toUpperCase();
  }

  // Ocultar menú de usuarios si no es ADMIN
  const navUsuarios = document.querySelector('[data-tab="usuarios"]');
  if (navUsuarios && user.rol !== 'ADMIN') {
    navUsuarios.style.display = 'none';
  }
}

async function cerrarSesion() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } finally {
    window.location.href = '/login';
  }
}

// =====================================================================
// NAVEGACIÓN ENTRE SECCIONES (TABS)
// =====================================================================

function configurarEventosNavegacion() {
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = item.getAttribute('data-tab');
      if (tabId) cambiarSeccion(tabId);
    });
  });

  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) btnLogout.addEventListener('click', cerrarSesion);
}

function cambiarSeccion(tabId) {
  AppState.activeTab = tabId;

  // Actualizar sidebar activo
  document.querySelectorAll('.nav-item').forEach((nav) => {
    nav.classList.toggle('active', nav.getAttribute('data-tab') === tabId);
  });

  // Mostrar sección activa
  document.querySelectorAll('.view-section').forEach((sec) => {
    sec.classList.remove('active');
  });

  const seccionDestino = document.getElementById(`section-${tabId}`);
  if (seccionDestino) seccionDestino.classList.add('active');

  // Acciones según sección
  if (tabId === 'dashboard') cargarDashboard();
  else if (tabId === 'contactos') cargarVistaContactos();
  else if (tabId === 'plantillas') cargarPlantillas();
  else if (tabId === 'campanas') cargarCampanas();
  else if (tabId === 'mensajes') cargarConversaciones();
  else if (tabId === 'usuarios') cargarUsuarios();
  else if (tabId === 'logs') cargarLogsEnVivo();
}

// =====================================================================
// SECCIÓN 1: DASHBOARD GENERAL
// =====================================================================

async function cargarDashboard() {
  try {
    const res = await fetch('/api/dashboard/metricas');
    if (!res.ok) return;
    const data = await res.json();
    AppState.metricas = data;

    renderizarMetricasDashboard(data.kpis, data.sistema);
    renderizarUltimosMensajes(data.ultimos_mensajes);
  } catch (e) {
    console.error('Error cargando métricas:', e);
  }
}

function renderizarMetricasDashboard(kpis, sistema) {
  // KPIs numéricos
  document.getElementById('kpi-total-mensajes').textContent = kpis.total_mensajes.toLocaleString();
  document.getElementById('kpi-entrantes').textContent = kpis.entrantes.toLocaleString();
  document.getElementById('kpi-salientes').textContent = kpis.salientes.toLocaleString();
  document.getElementById('kpi-tasa-entrega').textContent = `${kpis.tasa_entrega}%`;
  document.getElementById('kpi-tasa-lectura').textContent = `${kpis.tasa_lectura}%`;

  // Límite de 24 horas
  const limite = kpis.limite_24h;
  document.getElementById('kpi-24h-usados').textContent = limite.usados;
  document.getElementById('kpi-24h-disponibles').textContent = limite.disponibles;
  document.getElementById('kpi-24h-maximo').textContent = limite.maximo;

  const barFill = document.getElementById('quota-bar-fill');
  if (barFill) barFill.style.width = `${limite.porcentaje}%`;

  // Estado del sistema en barra superior
  const badgeMotor = document.getElementById('badge-db-engine');
  if (badgeMotor) {
    badgeMotor.textContent = sistema.motor_base_datos;
    badgeMotor.className = sistema.oracle_conectado ? 'badge badge-acepto' : 'badge badge-sent';
  }
}

function renderizarUltimosMensajes(mensajes) {
  const tbody = document.getElementById('tbody-ultimos-mensajes');
  if (!tbody) return;

  if (!mensajes || mensajes.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">Sin actividad reciente</td></tr>';
    return;
  }

  tbody.innerHTML = mensajes.map((m) => {
    const esEntrante = m.direccion === 'ENTRANTE';
    const badgeDir = esEntrante
      ? '<span class="badge badge-acepto"><i class="fas fa-arrow-down"></i> Entrante</span>'
      : '<span class="badge badge-read"><i class="fas fa-arrow-up"></i> Saliente</span>';

    const estadoPill = m.estado_status
      ? `<span class="badge badge-${m.estado_status.toLowerCase()}">${m.estado_status}</span>`
      : '-';

    const fechaFormateada = m.fecha_registro ? m.fecha_registro.replace('T', ' ').slice(0, 19) : '-';

    return `
      <tr>
        <td><strong>#${m.id_log}</strong></td>
        <td>${badgeDir}</td>
        <td>
          <div style="font-weight:600;">${m.wa_id || '-'}</div>
          <small class="text-muted">${m.wa_name || ''}</small>
        </td>
        <td>
          <span class="badge" style="background:#e2e8f0; color:#334155;">${m.tipo_mensaje || 'texto'}</span>
        </td>
        <td style="max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${m.texto_mensaje || ''}">
          ${m.texto_mensaje || '<em>(Sin texto)</em>'}
        </td>
        <td>${estadoPill}</td>
        <td class="text-muted" style="font-size:12px;">${fechaFormateada}</td>
      </tr>
    `;
  }).join('');
}

// =====================================================================
// SECCIÓN 2: CONTACTOS Y PADRÓN DE SOCIOS
// =====================================================================

async function cargarArchivosContactos() {
  try {
    const res = await fetch('/api/contactos/archivos');
    if (!res.ok) return;
    AppState.archivosCsv = await res.json();
    actualizarSelectorArchivosCsv();
  } catch (e) {
    console.error('Error cargando archivos de contactos:', e);
  }
}

function actualizarSelectorArchivosCsv() {
  const selects = [
    document.getElementById('select-archivo-contactos'),
    document.getElementById('wizard-select-csv'),
  ];

  selects.forEach((sel) => {
    if (!sel) return;
    sel.innerHTML = AppState.archivosCsv.map((a) => `
      <option value="${a.nombre}">${a.nombre} (${a.tamano_kb} KB)</option>
    `).join('');
  });

  if (AppState.archivosCsv.length > 0 && !AppState.archivoCsvSeleccionado) {
    AppState.archivoCsvSeleccionado = AppState.archivosCsv[0].nombre;
  }
}

async function cargarVistaContactos() {
  await cargarArchivosContactos();
  const select = document.getElementById('select-archivo-contactos');
  const archivo = select ? select.value : AppState.archivoCsvSeleccionado;
  if (!archivo) return;

  await cargarResumenYFilasContactos(archivo);
}

async function cargarResumenYFilasContactos(nombreArchivo) {
  try {
    // 1. Cargar resumen estadístico
    const resResumen = await fetch(`/api/contactos/resumen?archivo=${encodeURIComponent(nombreArchivo)}`);
    if (resResumen.ok) {
      const resumen = await resResumen.json();
      document.getElementById('contactos-total').textContent = resumen.total_filas;
      document.getElementById('contactos-con-acepto').textContent = resumen.con_consentimiento;
      document.getElementById('contactos-excluidos').textContent = resumen.excluidos_consentimiento;
      document.getElementById('contactos-validos').textContent = resumen.aptos_para_envio;
    }

    // 2. Cargar tabla de filas
    await filtrarTablaContactos();
  } catch (e) {
    console.error('Error cargando contactos:', e);
  }
}

async function filtrarTablaContactos() {
  const select = document.getElementById('select-archivo-contactos');
  const archivo = select ? select.value : AppState.archivoCsvSeleccionado;
  if (!archivo) return;

  const busqueda = (document.getElementById('input-busqueda-contactos')?.value || '').trim();
  const filtroConsentimiento = document.getElementById('filter-consentimiento')?.value || '';

  const params = new URLSearchParams({
    archivo: archivo,
    limite: '100',
    offset: '0',
  });
  if (busqueda) params.append('busqueda', busqueda);
  if (filtroConsentimiento) params.append('consentimiento', filtroConsentimiento);

  const tbody = document.getElementById('tbody-contactos');
  if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4">Cargando contactos...</td></tr>';

  try {
    const res = await fetch(`/api/contactos/filas?${params.toString()}`);
    if (!res.ok) return;
    const data = await res.json();
    renderizarFilasContactos(data.contactos);
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-danger">Error al cargar filas</td></tr>';
  }
}

function renderizarFilasContactos(contactos) {
  const tbody = document.getElementById('tbody-contactos');
  if (!tbody) return;

  if (!contactos || contactos.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No se encontraron contactos</td></tr>';
    return;
  }

  tbody.innerHTML = contactos.map((c) => {
    const esAcepto = c.consentimiento === 'ACEPTO';
    const badgeConsentimiento = esAcepto
      ? '<span class="badge badge-acepto"><i class="fas fa-check-circle"></i> ACEPTO</span>'
      : '<span class="badge badge-no-acepto">NO ACEPTO</span>';

    const telBadge = c.telefono_valido
      ? `<span style="font-family:monospace; font-weight:600; color:var(--primary);">${c.telefono_normalizado}</span>`
      : `<span class="badge badge-failed" title="${c.motivo_telefono}">Inválido (${c.motivo_telefono})</span>`;

    return `
      <tr>
        <td><strong>#${c.fila}</strong></td>
        <td>
          <div style="font-weight:700;">${c.nombre}</div>
          <small class="text-muted">DNI: ${c.dni || '-'} | Mat: ${c.matricula || '-'}</small>
        </td>
        <td>${c.email || '-'}</td>
        <td style="font-family:monospace;">${c.telefono_original}</td>
        <td>${telBadge}</td>
        <td>${badgeConsentimiento}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="probarPlantillaConContacto('${c.nombre}', '${c.telefono_normalizado || c.telefono_original}')">
            <i class="fab fa-whatsapp"></i> Probar
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

// Subida de archivos CSV
async function subirArchivoCsv() {
  const input = document.getElementById('input-file-csv');
  if (!input || !input.files || input.files.length === 0) {
    alert('Por favor selecciona un archivo CSV.');
    return;
  }

  const formData = new FormData();
  formData.append('archivo', input.files[0]);

  try {
    const res = await fetch('/api/contactos/subir', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (res.ok) {
      alert(`Archivo '${input.files[0].name}' subido y validado exitosamente.`);
      cerrarModal('modal-subir-csv');
      await cargarArchivosContactos();
      await cargarResumenYFilasContactos(data.resumen.archivo);
    } else {
      alert(`Error al subir: ${data.detail || 'Formato inválido'}`);
    }
  } catch (e) {
    alert(`Error de conexión: ${e}`);
  }
}

// =====================================================================
// SECCIÓN 3: PLANTILLAS Y SIMULADOR DE WHATSAPP
// =====================================================================

async function cargarPlantillas() {
  try {
    const res = await fetch('/api/plantillas');
    if (!res.ok) return;
    AppState.plantillas = await res.json();

    renderizarCatalogoPlantillas(AppState.plantillas);

    // Seleccionar la primera plantilla por defecto
    if (AppState.plantillas.length > 0 && !AppState.plantillaSeleccionada) {
      seleccionarPlantilla(AppState.plantillas[0].id);
    }
  } catch (e) {
    console.error('Error cargando plantillas:', e);
  }
}

function renderizarCatalogoPlantillas(plantillas) {
  const contenedor = document.getElementById('grid-plantillas');
  if (!contenedor) return;

  contenedor.innerHTML = plantillas.map((p) => {
    const badgeCategoria = p.categoria === 'UTILITY'
      ? '<span class="badge badge-utility">UTILITY</span>'
      : '<span class="badge badge-marketing">MARKETING</span>';

    const esSeleccionada = AppState.plantillaSeleccionada?.id === p.id;

    return `
      <div class="template-card ${esSeleccionada ? 'selected' : ''}" onclick="seleccionarPlantilla('${p.id}')">
        <div class="template-card-header">
          <div>
            <h4 class="template-card-title">${p.titulo}</h4>
            <small style="font-family:monospace; color:var(--text-light);">${p.id}</small>
          </div>
          ${badgeCategoria}
        </div>
        <p class="template-card-body">${p.descripcion}</p>
        <div class="template-vars-list">
          ${p.variables.length > 0
            ? p.variables.map((v) => `<span class="var-tag">{{${v}}}</span>`).join('')
            : '<span class="text-muted" style="font-size:11px;">(Sin variables)</span>'
          }
        </div>
      </div>
    `;
  }).join('');
}

function seleccionarPlantilla(idPlantilla) {
  const plantilla = AppState.plantillas.find((p) => p.id === idPlantilla);
  if (!plantilla) return;
  AppState.plantillaSeleccionada = plantilla;

  // Actualizar tarjeta seleccionada
  document.querySelectorAll('.template-card').forEach((c) => c.classList.remove('selected'));
  renderizarCatalogoPlantillas(AppState.plantillas);

  // Renderizar campos de variables en el panel lateral
  renderizarFormularioVariables(plantilla);

  // Actualizar vista previa en el celular de WhatsApp
  actualizarMockupWhatsApp();
}

function renderizarFormularioVariables(plantilla) {
  const contenedor = document.getElementById('template-vars-inputs');
  const titulo = document.getElementById('simulador-plantilla-titulo');
  const metaBadge = document.getElementById('simulador-meta-id');

  if (titulo) titulo.textContent = plantilla.titulo;
  if (metaBadge) metaBadge.textContent = `ID Meta: ${plantilla.id_meta || '-'}`;

  if (!contenedor) return;

  if (plantilla.variables.length === 0) {
    contenedor.innerHTML = '<p class="text-muted" style="font-size:13px;">Esta plantilla no requiere variables adicionales.</p>';
    return;
  }

  contenedor.innerHTML = plantilla.variables.map((v) => {
    const valEjemplo = plantilla.ejemplo[v] || '';
    return `
      <div class="form-group">
        <label class="form-label">Variable: <code>{{${v}}}</code></label>
        <input type="text" class="form-input var-input" data-var="${v}" value="${valEjemplo}" oninput="actualizarMockupWhatsApp()" placeholder="Valor para ${v}">
      </div>
    `;
  }).join('');
}

function actualizarMockupWhatsApp() {
  if (!AppState.plantillaSeleccionada) return;

  const valores = {};
  document.querySelectorAll('.var-input').forEach((inp) => {
    const varName = inp.getAttribute('data-var');
    valores[varName] = inp.value;
  });

  // Reemplazar texto
  let texto = AppState.plantillaSeleccionada.cuerpo;
  for (const [varName, val] of Object.entries(valores)) {
    const reemplazo = val ? `<span class="variable-highlight">${val}</span>` : `[${varName}]`;
    texto = texto.split(`{{${varName}}}`).join(reemplazo);
  }

  const contenedorBubble = document.getElementById('phone-bubble-text');
  if (contenedorBubble) {
    contenedorBubble.innerHTML = texto;
  }
}

async function verificarPlantillaEnMeta() {
  if (!AppState.plantillaSeleccionada) return;
  const id = AppState.plantillaSeleccionada.id;
  const badge = document.getElementById('status-meta-badge');
  if (badge) badge.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Consultando...';

  try {
    const res = await fetch(`/api/plantillas/${id}/verificar`);
    const data = await res.json();
    if (data.ok) {
      if (badge) badge.innerHTML = `<span class="badge badge-acepto"><i class="fas fa-check"></i> ${data.status}</span>`;
    } else {
      if (badge) badge.innerHTML = `<span class="badge badge-failed"><i class="fas fa-exclamation-triangle"></i> ${data.error || 'No verificado'}</span>`;
    }
  } catch (e) {
    if (badge) badge.innerHTML = '<span class="badge badge-failed">Error de conexión</span>';
  }
}

function probarPlantillaConContacto(nombre, telefono) {
  cambiarSeccion('plantillas');
  const inputNombre = document.querySelector('.var-input[data-var="nombre"]');
  if (inputNombre) {
    inputNombre.value = nombre;
    actualizarMockupWhatsApp();
  }
}

// =====================================================================
// SECCIÓN 4: ASISTENTE DE CAMPAÑAS Y ENVÍOS
// =====================================================================

async function cargarCampanas() {
  try {
    const res = await fetch('/api/campanas');
    if (!res.ok) return;
    AppState.campanas = await res.json();
    renderizarTablaCampanas(AppState.campanas);
  } catch (e) {
    console.error('Error cargando campañas:', e);
  }
}

function renderizarTablaCampanas(campanas) {
  const tbody = document.getElementById('tbody-campanas');
  if (!tbody) return;

  if (!campanas || campanas.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">Aún no se han ejecutado campañas</td></tr>';
    return;
  }

  tbody.innerHTML = campanas.map((c) => {
    const estadoBadge = c.estado === 'COMPLETADA'
      ? '<span class="badge badge-acepto"><i class="fas fa-check-double"></i> Completada</span>'
      : '<span class="badge badge-sent">Con errores</span>';

    return `
      <tr>
        <td><strong>${c.nombre}</strong></td>
        <td><span style="font-family:monospace; color:var(--primary);">${c.plantilla}</span></td>
        <td>${c.total_contactos}</td>
        <td><span class="badge badge-acepto">${c.exitosos}</span></td>
        <td><span class="badge badge-failed">${c.errores}</span></td>
        <td>${estadoBadge}</td>
        <td class="text-muted" style="font-size:12px;">${c.fecha}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="verDetalleLogCampana('${c.log_archivo}')">
            <i class="fas fa-file-alt"></i> Ver Log
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

// WIZARD PASO A PASO DE NUEVA CAMPAÑA
function abrirWizardCampana() {
  AppState.wizard = {
    paso: 1,
    plantilla: AppState.plantillas[0]?.id || '',
    archivoCsv: AppState.archivosCsv[0]?.nombre || '',
    mapeoColumnas: {},
    valoresFijos: {},
    simulacion: null,
  };

  actualizarPasoWizard(1);
  abrirModal('modal-wizard-campana');
}

function actualizarPasoWizard(paso) {
  AppState.wizard.paso = paso;

  // Actualizar nodos visuales del stepper
  document.querySelectorAll('.wizard-step-node').forEach((node) => {
    const nodePaso = parseInt(node.getAttribute('data-step'), 10);
    node.classList.toggle('active', nodePaso === paso);
    node.classList.toggle('completed', nodePaso < paso);
  });

  // Mostrar panel correspondiente
  document.querySelectorAll('.wizard-step-content').forEach((c) => {
    c.style.display = 'none';
  });
  const pasoActualEl = document.getElementById(`wizard-step-${paso}`);
  if (pasoActualEl) pasoActualEl.style.display = 'block';

  // Configuración de botones
  const btnAtras = document.getElementById('btn-wizard-atras');
  const btnSiguiente = document.getElementById('btn-wizard-siguiente');
  const btnEnviar = document.getElementById('btn-wizard-enviar');

  if (btnAtras) btnAtras.style.display = paso > 1 ? 'inline-flex' : 'none';
  if (btnSiguiente) btnSiguiente.style.display = paso < 4 ? 'inline-flex' : 'none';
  if (btnEnviar) btnEnviar.style.display = paso === 4 ? 'inline-flex' : 'none';

  // Lógica específica por paso
  if (paso === 1) {
    poblarWizardPaso1();
  } else if (paso === 2) {
    poblarWizardPaso2();
  } else if (paso === 3) {
    poblarWizardPaso3();
  } else if (paso === 4) {
    ejecutarSimulacionWizard();
  }
}

function poblarWizardPaso1() {
  const select = document.getElementById('wizard-select-plantilla');
  if (select) {
    select.innerHTML = AppState.plantillas.map((p) => `
      <option value="${p.id}" ${p.id === AppState.wizard.plantilla ? 'selected' : ''}>${p.titulo} (${p.id})</option>
    `).join('');
  }
}

function poblarWizardPaso2() {
  const select = document.getElementById('wizard-select-csv');
  if (select) {
    select.value = AppState.wizard.archivoCsv || AppState.archivosCsv[0]?.nombre || '';
  }
}

async function poblarWizardPaso3() {
  const plantillaId = document.getElementById('wizard-select-plantilla')?.value;
  const archivoCsv = document.getElementById('wizard-select-csv')?.value;
  AppState.wizard.plantilla = plantillaId;
  AppState.wizard.archivoCsv = archivoCsv;

  const plantilla = AppState.plantillas.find((p) => p.id === plantillaId);
  const contenedor = document.getElementById('wizard-mapping-container');
  if (!contenedor || !plantilla) return;

  // Obtener columnas disponibles del CSV
  const res = await fetch(`/api/contactos/resumen?archivo=${encodeURIComponent(archivoCsv)}`);
  const resumen = await res.json();
  const columnasDisponibles = resumen.columnas || [];

  if (plantilla.variables.length === 0) {
    contenedor.innerHTML = '<p class="text-muted">Esta plantilla no tiene variables. Puedes continuar a la simulación.</p>';
    return;
  }

  contenedor.innerHTML = plantilla.variables.map((v) => {
    // Si es "nombre", por defecto va a APEYNOM
    const esNombre = v === 'nombre';
    const columnaSugerida = esNombre ? 'APEYNOM' : (columnasDisponibles.find((c) => c.toLowerCase() === v.toLowerCase()) || '');

    return `
      <div class="card" style="margin-bottom:14px; padding:16px;">
        <h5 style="margin-bottom:8px;">Variable: <code style="color:var(--primary); font-size:14px;">{{${v}}}</code></h5>
        <div style="display:flex; gap:16px; flex-wrap:wrap;">
          <div style="flex:1; min-width:200px;">
            <label class="form-label">Origen:</label>
            <select class="form-input wizard-var-tipo" data-var="${v}" onchange="cambiarTipoOrigenVariable('${v}')">
              <option value="columna" ${columnaSugerida ? 'selected' : ''}>Tomar de columna del CSV (distinto para cada socio)</option>
              <option value="fijo" ${!columnaSugerida ? 'selected' : ''}>Texto fijo (igual para todo el envío)</option>
            </select>
          </div>
          <div style="flex:1; min-width:200px;" id="wrap-input-${v}">
            <label class="form-label">Columna del CSV:</label>
            <select class="form-input wizard-var-valor" data-var="${v}">
              ${columnasDisponibles.map((col) => `
                <option value="${col}" ${col === columnaSugerida ? 'selected' : ''}>${col}</option>
              `).join('')}
            </select>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function cambiarTipoOrigenVariable(variable) {
  const tipoSelect = document.querySelector(`.wizard-var-tipo[data-var="${variable}"]`);
  const wrap = document.getElementById(`wrap-input-${variable}`);
  if (!tipoSelect || !wrap) return;

  if (tipoSelect.value === 'fijo') {
    wrap.innerHTML = `
      <label class="form-label">Texto Fijo:</label>
      <input type="text" class="form-input wizard-var-valor" data-var="${variable}" placeholder="Ej: Agosto 2026">
    `;
  } else {
    poblarWizardPaso3(); // Recargar opciones de columnas
  }
}

async function ejecutarSimulacionWizard() {
  const container = document.getElementById('wizard-simulacion-results');
  if (container) container.innerHTML = '<div class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x"></i><p style="margin-top:8px;">Ejecutando simulación y validación de teléfonos...</p></div>';

  // Recolectar mapeo
  const mapeoColumnas = {};
  const valoresFijos = {};

  document.querySelectorAll('.wizard-var-tipo').forEach((select) => {
    const varName = select.getAttribute('data-var');
    const valorInput = document.querySelector(`.wizard-var-valor[data-var="${varName}"]`);
    if (select.value === 'columna') {
      mapeoColumnas[varName] = valorInput.value;
    } else {
      valoresFijos[varName] = valorInput.value;
    }
  });

  AppState.wizard.mapeoColumnas = mapeoColumnas;
  AppState.wizard.valoresFijos = valoresFijos;

  try {
    const res = await fetch('/api/campanas/simular', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nombre_plantilla: AppState.wizard.plantilla,
        archivo_csv: AppState.wizard.archivoCsv,
        columnas_mapeadas: mapeoColumnas,
        valores_fijos: valoresFijos,
      }),
    });

    const data = await res.json();
    AppState.wizard.simulacion = data;

    if (!res.ok) {
      if (container) container.innerHTML = `<div class="card p-4 text-danger"><i class="fas fa-times-circle"></i> Error en la simulación: ${data.detail}</div>`;
      return;
    }

    renderizarResultadosSimulacion(data);
  } catch (e) {
    if (container) container.innerHTML = `<div class="card p-4 text-danger">Error de conexión: ${e}</div>`;
  }
}

function renderizarResultadosSimulacion(data) {
  const container = document.getElementById('wizard-simulacion-results');
  if (!container) return;

  const advertenciasHtml = data.advertencias && data.advertencias.length > 0
    ? data.advertencias.map((a) => `<div class="badge badge-sent py-2 px-3" style="margin-bottom:12px; display:block;"><i class="fas fa-exclamation-triangle"></i> ${a}</div>`).join('')
    : '';

  const primerosMensajesHtml = data.primeros_mensajes.map((m, idx) => `
    <div style="background:var(--bg-surface-alt); border-radius:8px; padding:12px; margin-bottom:10px; border-left:3px solid var(--primary);">
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <strong>Destinatario #${idx + 1}: ${m.nombre}</strong>
        <span style="font-family:monospace; color:var(--primary); font-weight:600;">${m.destinatario}</span>
      </div>
      <div style="font-size:12px; white-space:pre-wrap; color:var(--text-main);">${m.texto_renderizado}</div>
    </div>
  `).join('');

  container.innerHTML = `
    ${advertenciasHtml}
    <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:16px;">
      <div class="kpi-card py-2 px-3">
        <div>
          <div class="kpi-value text-success">${data.se_van_a_enviar}</div>
          <div class="kpi-label">Se van a Enviar</div>
        </div>
      </div>
      <div class="kpi-card py-2 px-3">
        <div>
          <div class="kpi-value">${data.total_contactos_con_consentimiento}</div>
          <div class="kpi-label">Con Consentimiento</div>
        </div>
      </div>
      <div class="kpi-card py-2 px-3">
        <div>
          <div class="kpi-value text-muted">${data.excluidos_consentimiento}</div>
          <div class="kpi-label">Excluidos (No Acepto)</div>
        </div>
      </div>
      <div class="kpi-card py-2 px-3">
        <div>
          <div class="kpi-value text-danger">${data.numeros_invalidos_total}</div>
          <div class="kpi-label">Teléfonos Inválidos</div>
        </div>
      </div>
    </div>

    <h5 style="margin-bottom:10px;">Previsualización de los primeros mensajes:</h5>
    ${primerosMensajesHtml}
  `;
}

async function confirmarYEnviarCampana() {
  const nombreCampana = prompt('Por favor ingresa un nombre para identificar esta campaña:', `Campaña ${AppState.wizard.plantilla} - ${new Date().toLocaleDateString()}`);
  if (!nombreCampana) return;

  const btnEnviar = document.getElementById('btn-wizard-enviar');
  if (btnEnviar) {
    btnEnviar.disabled = true;
    btnEnviar.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
  }

  try {
    const res = await fetch('/api/campanas/enviar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nombre_campana: nombreCampana,
        nombre_plantilla: AppState.wizard.plantilla,
        archivo_csv: AppState.wizard.archivoCsv,
        columnas_mapeadas: AppState.wizard.mapeoColumnas,
        valores_fijos: AppState.wizard.valoresFijos,
        pausa_segundos: 0.2,
      }),
    });

    let data;
    try {
      data = await res.json();
    } catch {
      const texto = await res.text().catch(() => '');
      throw new Error(`Error en servidor (${res.status}): ${texto || 'Error interno no especificado'}`);
    }

    if (res.ok) {
      alert(`¡Campaña finalizada con éxito!\nTotal enviados: ${data.total_enviados}\nExitosos: ${data.exitosos}\nErrores: ${data.errores}\nLog guardado: ${data.log_archivo}`);
      cerrarModal('modal-wizard-campana');
      cambiarSeccion('campanas');
    } else {
      alert(`Error al enviar: ${data.detail || 'Ocurrió un problema'}`);
    }
  } catch (e) {
    alert(`Error de envío: ${e.message || e}`);
  } finally {
    if (btnEnviar) {
      btnEnviar.disabled = false;
      btnEnviar.innerHTML = '<i class="fab fa-whatsapp"></i> Confirmar y Enviar de Verdad';
    }
  }
}

async function verDetalleLogCampana(nombreLog) {
  try {
    const res = await fetch(`/api/campanas/logs/${encodeURIComponent(nombreLog)}`);
    if (!res.ok) return;
    const filas = await res.json();

    const tbody = document.getElementById('tbody-modal-log');
    if (tbody) {
      tbody.innerHTML = filas.map((f) => `
        <tr>
          <td><strong>${f.nombre}</strong></td>
          <td>${f.numero_original}</td>
          <td style="font-family:monospace; color:var(--primary);">${f.numero_normalizado || '-'}</td>
          <td><span class="badge badge-${f.resultado === 'OK' ? 'acepto' : 'failed'}">${f.resultado}</span></td>
          <td style="font-size:11px; max-width:240px; overflow:hidden; text-overflow:ellipsis;" title="${f.detalle}">${f.detalle}</td>
        </tr>
      `).join('');
    }

    abrirModal('modal-ver-log');
  } catch (e) {
    alert(`Error leyendo log: ${e}`);
  }
}

// =====================================================================
// SECCIÓN 5: USUARIOS Y ROLES (ADMIN)
// =====================================================================

async function cargarUsuarios() {
  if (AppState.usuario?.rol !== 'ADMIN') return;

  try {
    const res = await fetch('/api/usuarios');
    if (!res.ok) return;
    AppState.usuarios = await res.json();
    renderizarTablaUsuarios(AppState.usuarios);
  } catch (e) {
    console.error('Error cargando usuarios:', e);
  }
}

function renderizarTablaUsuarios(usuarios) {
  const tbody = document.getElementById('tbody-usuarios');
  if (!tbody) return;

  tbody.innerHTML = usuarios.map((u) => {
    const rolBadge = u.rol === 'ADMIN'
      ? '<span class="badge" style="background:#fee2e2; color:#b91c1c;">ADMIN</span>'
      : '<span class="badge" style="background:#e0f2fe; color:#0369a1;">OPERADOR</span>';

    const activoBadge = u.activo
      ? '<span class="badge badge-acepto">ACTIVO</span>'
      : '<span class="badge badge-no-acepto">INACTIVO</span>';

    return `
      <tr>
        <td><strong>${u.username}</strong></td>
        <td>${u.nombre_completo}</td>
        <td>${u.email || '-'}</td>
        <td>${rolBadge}</td>
        <td>${activoBadge}</td>
        <td class="text-muted" style="font-size:12px;">${u.ultimo_acceso || 'Nunca'}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="toggleEstadoUsuario(${u.id_usuario}, ${!u.activo}, '${u.nombre_completo}', '${u.email}', '${u.rol}')">
            ${u.activo ? 'Desactivar' : 'Activar'}
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

async function crearNuevoUsuario() {
  const username = document.getElementById('input-user-username')?.value.trim();
  const nombre = document.getElementById('input-user-nombre')?.value.trim();
  const email = document.getElementById('input-user-email')?.value.trim();
  const rol = document.getElementById('input-user-rol')?.value;
  const password = document.getElementById('input-user-password')?.value;

  if (!username || !nombre || !password) {
    alert('Por favor completa los campos obligatorios.');
    return;
  }

  try {
    const res = await fetch('/api/usuarios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username,
        nombre_completo: nombre,
        email: email,
        rol: rol,
        password: password,
      }),
    });

    const data = await res.json();
    if (res.ok) {
      alert(`Usuario '${username}' creado exitosamente.`);
      cerrarModal('modal-nuevo-usuario');
      await cargarUsuarios();
    } else {
      alert(`Error al crear usuario: ${data.detail}`);
    }
  } catch (e) {
    alert(`Error de red: ${e}`);
  }
}

async function toggleEstadoUsuario(id, nuevoActivo, nombre, email, rol) {
  try {
    const res = await fetch(`/api/usuarios/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nombre_completo: nombre,
        email: email,
        rol: rol,
        activo: nuevoActivo,
      }),
    });
    if (res.ok) {
      await cargarUsuarios();
    }
  } catch (e) {
    alert(`Error actualizando usuario: ${e}`);
  }
}

// =====================================================================
// SECCIÓN 6: LOGS EN VIVO
// =====================================================================

async function cargarLogsEnVivo() {
  const dirFiltro = document.getElementById('filter-logs-dir')?.value || '';
  const busqueda = (document.getElementById('input-busqueda-logs')?.value || '').trim();

  const params = new URLSearchParams({ limite: '100', offset: '0' });
  if (dirFiltro) params.append('direccion', dirFiltro);
  if (busqueda) params.append('busqueda', busqueda);

  const tbody = document.getElementById('tbody-logs-en-vivo');
  if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4">Cargando registros...</td></tr>';

  try {
    const res = await fetch(`/api/dashboard/mensajes?${params.toString()}`);
    if (!res.ok) return;
    const data = await res.json();

    if (!data.mensajes || data.mensajes.length === 0) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No hay registros con los filtros seleccionados</td></tr>';
      return;
    }

    if (tbody) {
      tbody.innerHTML = data.mensajes.map((m) => `
        <tr>
          <td><strong>#${m.id_log}</strong></td>
          <td><span class="badge badge-${m.direccion === 'ENTRANTE' ? 'acepto' : 'read'}">${m.direccion}</span></td>
          <td>
            <strong>${m.wa_id || '-'}</strong>
            <small class="text-muted">${m.wa_name ? ` (${m.wa_name})` : ''}</small>
          </td>
          <td><span class="badge" style="background:#f1f5f9; color:#475569;">${m.tipo_mensaje || '-'}</span></td>
          <td style="max-width:350px; font-size:12px; word-break:break-all;">${m.texto_mensaje || '<em>(Sin texto)</em>'}</td>
          <td style="font-size:12px;" class="text-muted">${m.fecha_registro}</td>
        </tr>
      `).join('');
    }
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-danger">Error de carga</td></tr>';
  }
}

// =====================================================================
// MODALES GENÉRICOS
// =====================================================================

function configurarModales() {
  document.querySelectorAll('.modal-overlay').forEach((overlay) => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.classList.remove('active');
      }
    });
  });
}

function abrirModal(idModal) {
  const modal = document.getElementById(idModal);
  if (modal) modal.classList.add('active');
}

function cerrarModal(idModal) {
  const modal = document.getElementById(idModal);
  if (modal) modal.classList.remove('active');
}

// =====================================================================
// SECCIÓN NUEVA: ENVÍO DE MENSAJES & CHAT EN VIVO
// =====================================================================

async function actualizarContadorPendientes() {
  try {
    const res = await fetch('/api/mensajes/conversaciones?filtro=pendientes');
    if (!res.ok) return;
    const data = await res.json();
    const pendientes = data.conversaciones ? data.conversaciones.length : 0;
    const badgeSidebar = document.getElementById('badge-mensajes-pendientes');
    const pillCount = document.getElementById('pill-count-pendientes');
    if (badgeSidebar) {
      if (pendientes > 0) {
        badgeSidebar.textContent = pendientes;
        badgeSidebar.style.display = 'inline-block';
      } else {
        badgeSidebar.style.display = 'none';
      }
    }
    if (pillCount) pillCount.textContent = pendientes;
  } catch (e) {
    console.error('Error actualizando contador de pendientes:', e);
  }
}

async function cargarConversaciones() {
  const contenedor = document.getElementById('lista-conversaciones-chat');
  if (contenedor && (!AppState.conversaciones || AppState.conversaciones.length === 0)) {
    contenedor.innerHTML = `
      <div class="text-center py-5 text-muted">
        <i class="fas fa-circle-notch fa-spin fa-2x mb-2" style="color:var(--primary);"></i>
        <p style="font-size:13px;">Cargando mensajes recibidos...</p>
      </div>`;
  }

  try {
    const res = await fetch(`/api/mensajes/conversaciones?filtro=${AppState.filtroChat}`);
    if (!res.ok) throw new Error('Error al consultar mensajes');
    const data = await res.json();
    AppState.conversaciones = data.conversaciones || [];

    // Actualizar badge de pendientes
    actualizarContadorPendientes();

    // Renderizar lista filtrada
    filtrarConversaciones();

    // Si había una conversación seleccionada, refrescarla
    if (AppState.conversacionActiva) {
      const existe = AppState.conversaciones.find((c) => c.wa_id === AppState.conversacionActiva.wa_id);
      if (existe) {
        seleccionarConversacion(AppState.conversacionActiva.wa_id, false);
      }
    }
  } catch (e) {
    console.error('Error cargando conversaciones:', e);
    if (contenedor) {
      contenedor.innerHTML = `
        <div class="text-center py-4 text-danger" style="font-size:13px;">
          <i class="fas fa-exclamation-triangle mb-2"></i>
          <p>No se pudieron cargar las conversaciones.</p>
          <button class="btn btn-secondary btn-sm mt-2" onclick="cargarConversaciones()">Reintentar</button>
        </div>`;
    }
  }
}

function filtrarConversaciones() {
  const busqueda = (document.getElementById('input-busqueda-chat')?.value || '').toLowerCase().trim();
  const contenedor = document.getElementById('lista-conversaciones-chat');
  if (!contenedor) return;

  let filtradas = AppState.conversaciones;
  if (busqueda) {
    filtradas = filtradas.filter((c) => {
      const matchNombre = (c.nombre || '').toLowerCase().includes(busqueda);
      const matchWa = (c.wa_id || '').includes(busqueda);
      const matchTexto = (c.ultimo_mensaje?.texto || '').toLowerCase().includes(busqueda);
      const matchMat = (c.socio_datos?.matricula || '').toLowerCase().includes(busqueda);
      return matchNombre || matchWa || matchTexto || matchMat;
    });
  }

  if (filtradas.length === 0) {
    contenedor.innerHTML = `
      <div class="text-center py-5 text-muted" style="padding: 30px 15px;">
        <i class="far fa-comment-dots fa-3x mb-3" style="opacity:0.4;"></i>
        <p style="font-size:13px; font-weight:600;">No se encontraron mensajes</p>
        <small style="color:var(--text-muted);">Prueba cambiando el filtro o la búsqueda</small>
      </div>`;
    return;
  }

  contenedor.innerHTML = filtradas.map((c) => {
    const esActiva = AppState.conversacionActiva && AppState.conversacionActiva.wa_id === c.wa_id;
    const iniciales = obtenerIniciales(c.nombre);
    const fechaRelativa = formatearFechaRelativa(c.ultimo_mensaje?.fecha);
    const esEntrante = c.ultimo_mensaje?.direccion === 'ENTRANTE';
    const tipo = c.ultimo_mensaje?.tipo;

    let iconoTipo = '';
    if (tipo === 'image') iconoTipo = '<i class="fas fa-image"></i> ';
    else if (tipo === 'interactive') iconoTipo = '<i class="fas fa-hand-pointer"></i> ';
    else if (tipo === 'template') iconoTipo = '<i class="fas fa-layer-group"></i> ';
    else if (!esEntrante) iconoTipo = '<i class="fas fa-reply" style="font-size:10px;"></i> ';

    const badgeEstado = c.pendiente
      ? '<span class="badge badge-error" style="font-size:10px;">Pendiente</span>'
      : (c.tiene_entrantes ? '<span class="badge badge-acepto" style="font-size:10px;"><i class="fas fa-check"></i> Respondido</span>' : '');

    const badgeSocio = c.es_socio && c.socio_datos?.matricula
      ? `<span class="badge badge-read" style="font-size:10px;">MP ${c.socio_datos.matricula}</span>`
      : '';

    return `
      <div class="chat-inbox-item ${esActiva ? 'active' : ''}" onclick="seleccionarConversacion('${c.wa_id}')">
        <div class="chat-inbox-avatar ${c.es_socio ? 'avatar-doctor' : ''}">
          ${iniciales}
          ${c.ventana_24h_activa ? '<div class="avatar-online-dot" title="Ventana 24h activa"></div>' : ''}
        </div>
        <div class="chat-inbox-info">
          <div class="chat-inbox-top-row">
            <span class="chat-inbox-name" title="${c.nombre}">${c.nombre}</span>
            <span class="chat-inbox-date">${fechaRelativa}</span>
          </div>
          <div class="chat-inbox-meta-row">
            ${badgeSocio}
            <span class="text-muted" style="font-size:11px;">+${c.wa_id}</span>
          </div>
          <div class="chat-inbox-preview-row">
            <span class="chat-inbox-snippet" title="${c.ultimo_mensaje?.texto || ''}">
              ${iconoTipo}${escapeHtml(c.ultimo_mensaje?.texto || '')}
            </span>
            ${badgeEstado}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function cambiarFiltroChat(filtro) {
  AppState.filtroChat = filtro;
  document.querySelectorAll('.chat-filter-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-filter') === filtro);
  });
  cargarConversaciones();
}

async function seleccionarConversacion(waId, scrollAbajo = true) {
  try {
    const res = await fetch(`/api/mensajes/conversacion/${waId}`);
    if (!res.ok) throw new Error('Error al cargar historial de conversación');
    const data = await res.json();
    AppState.conversacionActiva = data;

    // Actualizar sidebar activo
    document.querySelectorAll('.chat-inbox-item').forEach((item) => {
      const onclickAttr = item.getAttribute('onclick') || '';
      item.classList.toggle('active', onclickAttr.includes(waId));
    });

    // Mostrar panel activo y ocultar placeholder
    const emptyState = document.getElementById('chat-empty-state');
    const activeView = document.getElementById('chat-active-view');
    if (emptyState) emptyState.style.display = 'none';
    if (activeView) activeView.style.display = 'flex';

    // Rellenar cabecera
    const elNombre = document.getElementById('chat-header-nombre');
    const elAvatar = document.getElementById('chat-header-avatar');
    const elTelefono = document.getElementById('chat-header-telefono');
    const elMatricula = document.getElementById('chat-header-matricula');
    const elEmail = document.getElementById('chat-header-email');
    const elSocioBadge = document.getElementById('chat-header-socio-badge');
    const el24hBadge = document.getElementById('chat-header-24h-badge');

    if (elNombre) elNombre.textContent = data.nombre;
    if (elAvatar) elAvatar.textContent = obtenerIniciales(data.nombre);
    if (elTelefono) elTelefono.textContent = `+${data.wa_id}`;

    if (data.es_socio && data.socio_datos) {
      if (elSocioBadge) elSocioBadge.style.display = 'inline-block';
      if (elMatricula) {
        elMatricula.textContent = data.socio_datos.matricula ? `MP: ${data.socio_datos.matricula}` : '';
        elMatricula.style.display = data.socio_datos.matricula ? 'inline' : 'none';
      }
      if (elEmail) {
        elEmail.textContent = data.socio_datos.email ? `• ${data.socio_datos.email}` : '';
        elEmail.style.display = data.socio_datos.email ? 'inline' : 'none';
      }
    } else {
      if (elSocioBadge) elSocioBadge.style.display = 'none';
      if (elMatricula) elMatricula.style.display = 'none';
      if (elEmail) elEmail.style.display = 'none';
    }

    // Ventana 24 horas
    if (el24hBadge) {
      if (data.ventana_24h_activa) {
        el24hBadge.className = 'badge badge-acepto';
        el24hBadge.innerHTML = `<i class="fas fa-bolt"></i> Ventana 24h Activa (${data.tiempo_restante_24h})`;
        el24hBadge.title = 'Puedes responder con texto libre o con plantilla';
      } else {
        el24hBadge.className = 'badge badge-error';
        el24hBadge.innerHTML = `<i class="fas fa-lock"></i> Ventana 24h Cerrada`;
        el24hBadge.title = 'Meta requiere responder usando una plantilla oficial aprobada';
      }
    // Conmutar automáticamente el modo de respuesta según la ventana de Meta
    if (!data.ventana_24h_activa) {
      cambiarModoEnvioChat('plantilla');
    } else {
      cambiarModoEnvioChat('texto');
    }

    // Renderizar mensajes
    renderizarHistorialMensajes(data.mensajes);

    // Preparar selector de plantillas si está en modo plantilla
    if (AppState.modoEnvioChat === 'plantilla') {
      actualizarVariablesPlantillaChat();
    }

    // Scroll al final
    if (scrollAbajo) {
      setTimeout(() => {
        const scrollArea = document.getElementById('chat-messages-container');
        if (scrollArea) scrollArea.scrollTop = scrollArea.scrollHeight;
      }, 50);
    }
  } catch (e) {
    console.error('Error cargando conversación:', e);
    alert('No se pudo cargar el historial del mensaje.');
  }
}

function recargarConversacionActiva() {
  if (AppState.conversacionActiva) {
    seleccionarConversacion(AppState.conversacionActiva.wa_id, false);
  }
  cargarConversaciones();
}

function renderizarHistorialMensajes(mensajes) {
  const container = document.getElementById('chat-messages-container');
  if (!container) return;

  if (!mensajes || mensajes.length === 0) {
    container.innerHTML = `
      <div class="text-center py-5 text-muted">
        <i class="far fa-comments fa-2x mb-2" style="opacity:0.5;"></i>
        <p style="font-size:13px;">No hay mensajes registrados en esta conversación.</p>
      </div>`;
    return;
  }

  let html = '';
  let fechaAnterior = '';

  mensajes.forEach((m) => {
    // Agrupador por día
    const fechaSoloDia = m.fecha ? m.fecha.split(' ')[0] : '';
    if (fechaSoloDia && fechaSoloDia !== fechaAnterior) {
      html += `
        <div class="chat-bubble-wrap system">
          <div class="wsp-date-pill">${formatearFechaDia(fechaSoloDia)}</div>
        </div>`;
      fechaAnterior = fechaSoloDia;
    }

    const esEntrante = m.direccion === 'ENTRANTE';
    const hora = m.fecha ? m.fecha.substring(11, 16) : '';

    // Manejo de eventos de status de campañas salientes
    if (!esEntrante && m.tipo === 'status') {
      html += `
        <div class="chat-bubble-wrap system">
          <div class="chat-bubble-box system-pill">
            <i class="fas fa-info-circle"></i> Notificación de entrega: <strong>${m.texto}</strong> (${hora})
          </div>
        </div>`;
      return;
    }

    let checkmarkHtml = '';
    if (!esEntrante) {
      const st = (m.estado_status || 'sent').toLowerCase();
      if (st === 'read') {
        checkmarkHtml = '<span class="chat-checkmarks read" title="Leído"><i class="fas fa-check-double"></i></span>';
      } else if (st === 'delivered') {
        checkmarkHtml = '<span class="chat-checkmarks" title="Entregado"><i class="fas fa-check-double"></i></span>';
      } else if (st === 'failed') {
        checkmarkHtml = '<span class="text-danger" title="Error de entrega"><i class="fas fa-exclamation-circle"></i></span>';
      } else {
        checkmarkHtml = '<span class="chat-checkmarks" title="Enviado"><i class="fas fa-check"></i></span>';
      }
    }

    let contenidoHtml = escapeHtml(m.texto);
    if (m.tipo === 'image') {
      contenidoHtml = `
        <div style="font-weight:600; color:var(--primary); margin-bottom:4px;">
          <i class="fas fa-image"></i> [Imagen / Foto de Credencial]
        </div>
        <div>${escapeHtml(m.texto || 'Archivo adjunto recibido')}</div>`;
    } else if (m.tipo === 'interactive') {
      contenidoHtml = `
        <div style="font-weight:600; color:var(--success); margin-bottom:4px;">
          <i class="fas fa-hand-pointer"></i> [Respuesta Interactiva]
        </div>
        <div>${escapeHtml(m.texto)}</div>`;
    } else if (m.tipo === 'template') {
      contenidoHtml = `
        <div style="font-size:10.5px; font-weight:700; color:var(--primary); margin-bottom:4px;">
          <i class="fas fa-layer-group"></i> Plantilla Oficial Meta
        </div>
        <div>${contenidoHtml}</div>`;
    }

    const textoEscapeCitar = (m.texto || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
    const nombreRemitente = esEntrante ? (AppState.conversacionActiva?.nombre || 'Socio') : 'Círculo Médico';

    html += `
      <div class="chat-bubble-wrap ${esEntrante ? 'incoming' : 'outgoing'}">
        <div class="chat-bubble-box ${esEntrante ? 'incoming' : 'outgoing'}">
          ${esEntrante ? `<div class="chat-bubble-sender">${nombreRemitente}</div>` : ''}
          <div class="chat-bubble-text">${contenidoHtml}</div>
          <div class="chat-bubble-footer">
            <span>${hora}</span>
            ${checkmarkHtml}
          </div>
          ${esEntrante ? `
            <button class="chat-bubble-action-btn" onclick="citarMensaje('${m.id_log}', '${nombreRemitente}', '${textoEscapeCitar}', '${m.wsp_msg_id}')" title="Responder a este mensaje">
              <i class="fas fa-reply"></i>
            </button>
          ` : ''}
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function citarMensaje(idLog, remitente, texto, wspMsgId) {
  AppState.mensajeCitar = { idLog, remitente, texto, wspMsgId };
  const quoteBar = document.getElementById('chat-quote-bar');
  const quoteSender = document.getElementById('quote-sender-name');
  const quoteText = document.getElementById('quote-text-snippet');

  if (quoteSender) quoteSender.textContent = `Respondiendo a ${remitente}`;
  if (quoteText) quoteText.textContent = texto;
  if (quoteBar) quoteBar.style.display = 'flex';

  const input = document.getElementById('input-chat-respuesta');
  if (input) input.focus();
}

function cancelarCitaMensaje() {
  AppState.mensajeCitar = null;
  const quoteBar = document.getElementById('chat-quote-bar');
  if (quoteBar) quoteBar.style.display = 'none';
}

function cambiarModoEnvioChat(modo) {
  AppState.modoEnvioChat = modo;
  const btnTexto = document.getElementById('btn-mode-texto');
  const btnPlantilla = document.getElementById('btn-mode-plantilla');
  const composerTexto = document.getElementById('chat-composer-texto');
  const composerPlantilla = document.getElementById('chat-composer-plantilla');

  if (modo === 'texto') {
    if (btnTexto) btnTexto.classList.add('active');
    if (btnPlantilla) btnPlantilla.classList.remove('active');
    if (composerTexto) composerTexto.style.display = 'block';
    if (composerPlantilla) composerPlantilla.style.display = 'none';
  } else {
    if (btnTexto) btnTexto.classList.remove('active');
    if (btnPlantilla) btnPlantilla.classList.add('active');
    if (composerTexto) composerTexto.style.display = 'none';
    if (composerPlantilla) composerPlantilla.style.display = 'block';
    cargarSelectPlantillasChat();
  }
}

function cargarSelectPlantillasChat() {
  const select = document.getElementById('chat-select-plantilla');
  if (!select) return;

  if (select.children.length === 0 && AppState.plantillas.length > 0) {
    select.innerHTML = AppState.plantillas.map((p) => `
      <option value="${p.nombre}">${p.nombre} (${p.categoria || 'OFICIAL'})</option>
    `).join('');
  }
  actualizarVariablesPlantillaChat();
}

function actualizarVariablesPlantillaChat() {
  const select = document.getElementById('chat-select-plantilla');
  const varsContainer = document.getElementById('chat-template-variables-container');
  if (!select || !varsContainer) return;

  const nombrePlantilla = select.value;
  const plantilla = AppState.plantillas.find((p) => p.nombre === nombrePlantilla);
  if (!plantilla) return;

  const vars = plantilla.variables || [];
  const socioNombre = AppState.conversacionActiva?.nombre || '';

  varsContainer.innerHTML = vars.map((v) => {
    let valorDefecto = '';
    if (v === 'nombre') valorDefecto = socioNombre;
    return `
      <div class="form-group" style="margin-bottom:8px;">
        <label class="form-label" style="font-size:11px; margin-bottom:2px;">Variable {{${v}}}:</label>
        <input type="text" class="form-input chat-template-var-input" data-var="${v}" value="${escapeHtml(valorDefecto)}" placeholder="Valor para ${v}..." oninput="actualizarPreviewPlantillaChat()">
      </div>
    `;
  }).join('');

  actualizarPreviewPlantillaChat();
}

function actualizarPreviewPlantillaChat() {
  const select = document.getElementById('chat-select-plantilla');
  const previewText = document.getElementById('chat-template-preview-text');
  if (!select || !previewText) return;

  const plantilla = AppState.plantillas.find((p) => p.nombre === select.value);
  if (!plantilla) return;

  let cuerpo = plantilla.cuerpo || plantilla.descripcion || '';
  document.querySelectorAll('.chat-template-var-input').forEach((input) => {
    const varName = input.getAttribute('data-var');
    const val = input.value.trim() || `[${varName}]`;
    cuerpo = cuerpo.split(`{{${varName}}}`).join(val);
  });

  previewText.innerHTML = cuerpo ? escapeHtml(cuerpo) : '<em>Vista previa del mensaje</em>';
}

function insertarRespuestaRapida(texto) {
  const input = document.getElementById('input-chat-respuesta');
  if (!input) return;
  input.value = texto;
  input.focus();
}

function handleChatKeyDown(event) {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    enviarRespuestaChat();
  }
}

async function enviarRespuestaChat() {
  if (!AppState.conversacionActiva) {
    alert('Por favor selecciona una conversación para responder.');
    return;
  }

  const waId = AppState.conversacionActiva.wa_id;
  const modo = AppState.modoEnvioChat;

  if (modo === 'texto' && AppState.conversacionActiva && !AppState.conversacionActiva.ventana_24h_activa) {
    const cambiar = confirm(
      '⚠️ Atención: La ventana de atención de 24 horas de Meta está CERRADA para este contacto ' +
      '(el socio no ha enviado mensajes en las últimas 24 horas).\n\n' +
      'Meta NO entregará respuestas de texto libre mientras la ventana esté cerrada. ' +
      'Para contactarlo ahora, debes enviar una Plantilla Oficial Aprobada.\n\n' +
      '¿Deseas cambiar ahora al modo "Usar Plantilla Aprobada"?'
    );
    if (cambiar) {
      cambiarModoEnvioChat('plantilla');
    }
    return;
  }

  const btnEnviar = modo === 'texto'
    ? document.getElementById('btn-enviar-texto')
    : document.getElementById('btn-enviar-plantilla-chat');

  let payload = {
    wa_id: waId,
    tipo_envio: modo,
    wsp_msg_id_contexto: AppState.mensajeCitar?.wspMsgId || null,
  };

  if (modo === 'texto') {
    const textarea = document.getElementById('input-chat-respuesta');
    const texto = (textarea?.value || '').trim();
    if (!texto) {
      alert('Por favor escribe un mensaje de respuesta.');
      if (textarea) textarea.focus();
      return;
    }
    payload.texto = texto;
  } else {
    const select = document.getElementById('chat-select-plantilla');
    const nombrePlantilla = select?.value;
    if (!nombrePlantilla) {
      alert('Por favor selecciona una plantilla.');
      return;
    }
    payload.nombre_plantilla = nombrePlantilla;
    payload.parametros_plantilla = {};
    document.querySelectorAll('.chat-template-var-input').forEach((input) => {
      const v = input.getAttribute('data-var');
      payload.parametros_plantilla[v] = input.value.trim();
    });
  }

  if (btnEnviar) {
    btnEnviar.disabled = true;
    btnEnviar.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Enviando...';
  }

  try {
    const res = await fetch('/api/mensajes/responder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      if (data.es_error_24h) {
        const cambiar = confirm(
          '⚠️ La ventana de 24 horas para respuestas libres de Meta está cerrada.\n\n' +
          'Para contactar al socio debes usar una plantilla oficial aprobada.\n\n' +
          '¿Deseas cambiar ahora al modo de Plantilla Oficial?'
        );
        if (cambiar) {
          cambiarModoEnvioChat('plantilla');
        }
      } else {
        alert(`Error al enviar mensaje: ${data.error || 'Respuesta fallida de Meta'}`);
      }
      return;
    }

    // Éxito: Limpiar input y cita
    if (modo === 'texto') {
      const textarea = document.getElementById('input-chat-respuesta');
      if (textarea) textarea.value = '';
    }
    cancelarCitaMensaje();

    // Recargar historial y lista
    await seleccionarConversacion(waId, true);
    await cargarConversaciones();
  } catch (e) {
    console.error('Error enviando respuesta:', e);
    alert(`Error de conexión al enviar mensaje: ${e}`);
  } finally {
    if (btnEnviar) {
      btnEnviar.disabled = false;
      btnEnviar.innerHTML = modo === 'texto'
        ? '<i class="fas fa-paper-plane"></i> <span>Enviar</span>'
        : '<i class="fab fa-whatsapp"></i> Enviar Plantilla Oficial';
    }
  }
}

// Utilidades de formato
function formatearFechaRelativa(fechaStr) {
  if (!fechaStr) return '';
  try {
    const limpia = fechaStr.split('.')[0].replace('T', ' ');
    const hoyStr = new Date().toISOString().split('T')[0];
    const fechaDia = limpia.split(' ')[0];
    const hora = limpia.substring(11, 16);
    if (fechaDia === hoyStr) return hora;
    const partes = fechaDia.split('-');
    return `${partes[2]}/${partes[1]}`;
  } catch (e) {
    return '';
  }
}

function formatearFechaDia(diaStr) {
  if (!diaStr) return 'Fecha';
  try {
    const hoyStr = new Date().toISOString().split('T')[0];
    if (diaStr === hoyStr) return 'HOY';
    const partes = diaStr.split('-');
    const meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
    const mes = meses[parseInt(partes[1], 10) - 1] || partes[1];
    return `${partes[2]} de ${mes} ${partes[0]}`;
  } catch (e) {
    return diaStr;
  }
}

function obtenerIniciales(nombre) {
  if (!nombre) return 'CM';
  const palabras = nombre.trim().replace(/^Dr\.\s*|^Dra\.\s*/i, '').split(/\s+/);
  if (palabras.length >= 2) {
    return (palabras[0][0] + palabras[1][0]).toUpperCase();
  }
  return palabras[0].substring(0, 2).toUpperCase();
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
