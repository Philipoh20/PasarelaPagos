/**
 * Pasarela de Pagos & Facturación JSON - Frontend Principal
 * Gestión completa de transacciones, emisión electrónica con firma SHA-256,
 * Dashboard analítico, CRUD de usuarios para administradores y control RBAC.
 */

const AppState = {
  token: localStorage.getItem('pasarela_jwt_token') || null,
  usuarioActual: null,
  pagos: [],
  facturas: [],
  usuarios: [],
  pagoSeleccionadoParaFacturar: null,
  pagoEnEdicionId: null,
  accionConfirmacion: null, // Función y metadatos para modal destructivo
};

const THEME_STORAGE_KEY = 'pasarela_theme';
const THEME_DARK = 'dark';

// Inicialización de tema oscuro / claro
document.documentElement.dataset.theme =
  localStorage.getItem(THEME_STORAGE_KEY) === THEME_DARK ? THEME_DARK : 'light';

// ==============================================================================
// INICIALIZACIÓN DE LA APLICACIÓN
// ==============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  configurarTema();
  configurarEventosUI();
  configurarNavegacionPorTeclado();

  if (AppState.token) {
    const sesionValida = await verificarSesionActual();
    if (sesionValida) {
      activarVistaAutenticada();
      await cargarTodo();
      // Mostrar por defecto la pestaña de Dashboard tras ingresar
      cambiarPestana('tab-dashboard', document.getElementById('tab-btn-dashboard'));
    } else {
      activarVistaNoAutenticada();
    }
  } else {
    activarVistaNoAutenticada();
  }
});

// ==============================================================================
// CLIENTE HTTP CENTRALIZADO (MANEJO DE 401 TOKEN VENCIDO Y 403 FORBIDDEN - UI01)
// ==============================================================================

async function apiFetch(url, options = {}) {
  const headers = Object.assign(
    { 'Content-Type': 'application/json' },
    options.headers || {}
  );

  if (AppState.token) {
    headers['Authorization'] = `Bearer ${AppState.token}`;
  }

  const fetchOptions = Object.assign({}, options, { headers });

  try {
    const response = await fetch(url, fetchOptions);
    let data = null;

    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }

    // UI01: Al vencer o rechazarse el token, informar lo ocurrido y permitir volver a ingresar.
    // No mostrar una sesión válida si la API rechazó el acceso.
    if (response.status === 401) {
      manejarTokenRechazado(data?.error || 'Tu sesión ha expirado o el token de acceso es inválido.');
      return { ok: false, status: 401, data };
    }

    if (response.status === 403) {
      lanzarToast(
        'forbidden',
        '403 FORBIDDEN',
        data?.error || 'Acceso denegado: tu rol no tiene autorización para realizar esta acción.'
      );
    }

    return {
      ok: response.ok,
      status: response.status,
      data
    };
  } catch (error) {
    lanzarToast('error', 'ERROR DE RED', error.message || 'No se pudo conectar con el servidor.');
    return { ok: false, status: 0, error };
  }
}

function manejarTokenRechazado(mensajeError) {
  // Limpiar sesión de forma segura
  AppState.token = null;
  AppState.usuarioActual = null;
  AppState.pagos = [];
  AppState.facturas = [];
  AppState.usuarios = [];
  localStorage.removeItem('pasarela_jwt_token');

  activarVistaNoAutenticada();

  const alertBox = document.getElementById('auth-alert-box');
  if (alertBox) {
    alertBox.textContent = `Sesión expirada: ${mensajeError} Por favor, inicia sesión de nuevo.`;
    alertBox.classList.remove('hidden');
  }

  lanzarToast(
    'error',
    'SESIÓN EXPIRADA',
    'El token fue rechazado o venció. Inicia sesión nuevamente para continuar.'
  );
}

// ==============================================================================
// AUTENTICACIÓN Y CONTROL DE VISTAS (LOGIN VS APLICACIÓN)
// ==============================================================================

async function verificarSesionActual() {
  if (!AppState.token) return false;

  const res = await apiFetch('/auth/me');
  if (res.ok && res.data) {
    AppState.usuarioActual = {
      username: res.data.username,
      rol: res.data.rol
    };
    actualizarBadgesUsuario();
    return true;
  }
  return false;
}

async function iniciarSesion(username, password) {
  const btnSubmit = document.getElementById('btn-submit-login');
  const txtSubmit = document.getElementById('btn-login-text');
  const alertBox = document.getElementById('auth-alert-box');
  if (alertBox) alertBox.classList.add('hidden');

  if (!username || !password) {
    mostrarErrorAuth('Por favor ingresa usuario y contraseña.');
    return;
  }

  if (btnSubmit) btnSubmit.disabled = true;
  if (txtSubmit) txtSubmit.innerHTML = '<span class="spinner"></span> Validando credenciales...';

  try {
    const res = await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Credenciales incorrectas');
    }

    AppState.token = data.token;
    AppState.usuarioActual = data.usuario;
    localStorage.setItem('pasarela_jwt_token', data.token);

    activarVistaAutenticada();
    actualizarBadgesUsuario();

    lanzarToast(
      'success',
      'ACCESO AUTORIZADO',
      `Bienvenido, ${data.usuario.username.toUpperCase()} (Rol: ${data.usuario.rol.toUpperCase()}).`
    );

    await cargarTodo();
    cambiarPestana('tab-dashboard', document.getElementById('tab-btn-dashboard'));
  } catch (err) {
    mostrarErrorAuth(err.message || 'Error al iniciar sesión.');
  } finally {
    if (btnSubmit) btnSubmit.disabled = false;
    if (txtSubmit) txtSubmit.innerHTML = 'INGRESAR AL SISTEMA &rarr;';
  }
}

async function registrarUsuarioNormal(username, password, email) {
  const btnSubmit = document.getElementById('btn-submit-registro');
  const txtSubmit = document.getElementById('btn-registro-text');
  const alertBox = document.getElementById('auth-alert-box');
  if (alertBox) alertBox.classList.add('hidden');

  if (btnSubmit) btnSubmit.disabled = true;
  if (txtSubmit) txtSubmit.innerHTML = '<span class="spinner"></span> Registrando cuenta...';

  try {
    const res = await fetch('/registro', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username,
        password,
        email: email || null,
        rol: 'usuario' // Siempre usuario regular por registro público
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Error al crear la cuenta');
    }

    lanzarToast('success', 'REGISTRO EXITOSO', 'Tu cuenta ha sido creada. Iniciando sesión...');
    await iniciarSesion(username, password);
  } catch (err) {
    mostrarErrorAuth(err.message || 'No se pudo completar el registro.');
  } finally {
    if (btnSubmit) btnSubmit.disabled = false;
    if (txtSubmit) txtSubmit.innerHTML = 'CREAR CUENTA E INGRESAR &rarr;';
  }
}

function cerrarSesion(mostrarMensaje = true) {
  AppState.token = null;
  AppState.usuarioActual = null;
  AppState.pagos = [];
  AppState.facturas = [];
  AppState.usuarios = [];
  localStorage.removeItem('pasarela_jwt_token');

  activarVistaNoAutenticada();

  if (mostrarMensaje) {
    lanzarToast('info', 'SESIÓN CERRADA', 'Has salido del sistema de forma segura.');
  }
}

function activarVistaAutenticada() {
  document.getElementById('view-unlogged')?.classList.add('hidden');
  document.getElementById('view-logged')?.classList.remove('hidden');
  document.getElementById('main-nav-bar')?.classList.remove('hidden');
  document.getElementById('header-user-box')?.classList.remove('hidden');

  const esAdmin = AppState.usuarioActual?.rol === 'admin';
  const tabUsuariosBtn = document.getElementById('tab-btn-usuarios');
  const tabUsuariosPane = document.getElementById('tab-usuarios');
  const dashIrUsuariosBtn = document.getElementById('btn-dash-ir-usuarios');

  if (esAdmin) {
    tabUsuariosBtn?.classList.remove('hidden');
    dashIrUsuariosBtn?.classList.remove('hidden');
  } else {
    tabUsuariosBtn?.classList.add('hidden');
    dashIrUsuariosBtn?.classList.add('hidden');
    tabUsuariosPane?.classList.add('hidden');
  }
}

function activarVistaNoAutenticada() {
  document.getElementById('view-unlogged')?.classList.remove('hidden');
  document.getElementById('view-logged')?.classList.add('hidden');
  document.getElementById('main-nav-bar')?.classList.add('hidden');
  document.getElementById('header-user-box')?.classList.add('hidden');

  // Limpiar campos de formularios
  document.getElementById('form-login')?.reset();
  document.getElementById('form-registro-normal')?.reset();

  // Resetear a pestaña login
  document.getElementById('btn-switch-login')?.click();
}

function mostrarErrorAuth(mensaje) {
  const alertBox = document.getElementById('auth-alert-box');
  if (alertBox) {
    alertBox.textContent = mensaje;
    alertBox.classList.remove('hidden');
  }
  lanzarToast('error', 'AUTENTICACIÓN', mensaje);
}

function actualizarBadgesUsuario() {
  if (!AppState.usuarioActual) return;
  const { username, rol } = AppState.usuarioActual;
  const topName = document.getElementById('top-user-name');
  const topRole = document.getElementById('top-user-role');
  if (topName) topName.textContent = username;
  if (topRole) {
    topRole.textContent = rol.toUpperCase();
    topRole.className = `user-role-tag ${rol}`;
  }
}

// ==============================================================================
// CONFIGURACIÓN DE EVENTOS UI Y NAVEGACIÓN
// ==============================================================================

function configurarEventosUI() {
  // Pestañas de navegación principal
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.getAttribute('data-tab');
      cambiarPestana(tabId, btn);
      // Cerrar menú móvil al navegar
      document.getElementById('main-nav-bar')?.classList.remove('mobile-open');
    });
  });

  // Menú hamburguesa móvil
  const mobileToggle = document.getElementById('mobile-nav-toggle');
  mobileToggle?.addEventListener('click', () => {
    const navBar = document.getElementById('main-nav-bar');
    const abierto = navBar?.classList.toggle('mobile-open');
    mobileToggle.setAttribute('aria-expanded', String(abierto));
  });

  // Alternador entre Login y Registro en pantalla de acceso
  const btnSwitchLogin = document.getElementById('btn-switch-login');
  const btnSwitchRegistro = document.getElementById('btn-switch-registro');
  const formLogin = document.getElementById('form-login');
  const formRegistro = document.getElementById('form-registro-normal');
  const alertBox = document.getElementById('auth-alert-box');

  btnSwitchLogin?.addEventListener('click', () => {
    btnSwitchLogin.classList.add('active');
    btnSwitchRegistro?.classList.remove('active');
    formLogin?.classList.add('active');
    formRegistro?.classList.remove('active');
    if (alertBox) alertBox.classList.add('hidden');
  });

  btnSwitchRegistro?.addEventListener('click', () => {
    btnSwitchRegistro.classList.add('active');
    btnSwitchLogin?.classList.remove('active');
    formRegistro?.classList.add('active');
    formLogin?.classList.remove('active');
    if (alertBox) alertBox.classList.add('hidden');
  });

  // Formulario Login
  formLogin?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const u = document.getElementById('login-username').value.trim();
    const p = document.getElementById('login-password').value;
    await iniciarSesion(u, p);
  });

  // Formulario Registro Normal
  formRegistro?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const u = document.getElementById('registro-username').value.trim();
    const p = document.getElementById('registro-password').value;
    const em = document.getElementById('registro-email').value.trim();
    await registrarUsuarioNormal(u, p, em);
  });

  // Cerrar sesión
  document.getElementById('btn-logout-header')?.addEventListener('click', () => cerrarSesion(true));

  // Actualizar Dashboard
  document.getElementById('btn-actualizar-dashboard')?.addEventListener('click', cargarDashboard);

  // Accesos rápidos en Dashboard
  document.getElementById('btn-dash-nuevo-pago')?.addEventListener('click', () => {
    cambiarPestana('tab-pagos', document.getElementById('tab-btn-pagos'));
    abrirModalNuevoPago();
  });

  document.getElementById('btn-dash-nueva-factura')?.addEventListener('click', () => {
    cambiarPestana('tab-facturas', document.getElementById('tab-btn-facturas'));
    abrirModalFactura();
  });

  document.getElementById('btn-dash-ir-divisas')?.addEventListener('click', () => {
    cambiarPestana('tab-divisas', document.getElementById('tab-btn-divisas'));
  });

  document.getElementById('btn-dash-ir-usuarios')?.addEventListener('click', () => {
    cambiarPestana('tab-usuarios', document.getElementById('tab-btn-usuarios'));
  });

  // Modales
  document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => {
      cerrarModal(btn.getAttribute('data-close'));
    });
  });

  document.querySelectorAll('.editorial-modal-backdrop').forEach(modal => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) cerrarModal(modal.id);
    });
  });

  // Pagos: Abrir modal nuevo pago
  document.getElementById('btn-abrir-modal-pago')?.addEventListener('click', abrirModalNuevoPago);
  document.getElementById('form-nuevo-pago')?.addEventListener('submit', guardarPago);

  // Facturas: Abrir modal emitir factura
  document.getElementById('btn-abrir-modal-factura')?.addEventListener('click', abrirModalFactura);
  document.getElementById('form-nueva-factura')?.addEventListener('submit', guardarNuevaFactura);
  document.querySelectorAll('input[name="modo-factura"]').forEach(radio => {
    radio.addEventListener('change', alternarModoFactura);
  });
  document.getElementById('factura-pago-id')?.addEventListener('change', alSeleccionarPagoEnFactura);
  document.getElementById('factura-iva-porcentaje')?.addEventListener('input', recalcularTotalesFactura);
  document.getElementById('btn-agregar-item')?.addEventListener('click', () => agregarFilaItemFactura());

  // Usuarios (Admin): Abrir modal nuevo usuario y submit
  document.getElementById('btn-abrir-modal-usuario')?.addEventListener('click', abrirModalNuevoUsuario);
  document.getElementById('form-nuevo-usuario')?.addEventListener('submit', guardarNuevoUsuarioAdmin);
  document.getElementById('form-editar-usuario')?.addEventListener('submit', guardarEdicionUsuario);

  // Filtros en vivo
  document.getElementById('filtro-pagos-cliente')?.addEventListener('input', filtrarPagos);
  document.getElementById('filtro-pagos-estado')?.addEventListener('change', filtrarPagos);
  document.getElementById('filtro-pagos-metodo')?.addEventListener('change', filtrarPagos);
  document.getElementById('btn-limpiar-filtros-pagos')?.addEventListener('click', () => {
    document.getElementById('filtro-pagos-cliente').value = '';
    document.getElementById('filtro-pagos-estado').value = '';
    document.getElementById('filtro-pagos-metodo').value = '';
    filtrarPagos();
  });

  document.getElementById('filtro-facturas-query')?.addEventListener('input', filtrarFacturas);
  document.getElementById('filtro-facturas-estado')?.addEventListener('change', filtrarFacturas);
  document.getElementById('btn-limpiar-filtros-facturas')?.addEventListener('click', () => {
    document.getElementById('filtro-facturas-query').value = '';
    document.getElementById('filtro-facturas-estado').value = '';
    filtrarFacturas();
  });

  document.getElementById('filtro-usuarios-query')?.addEventListener('input', filtrarUsuarios);
  document.getElementById('filtro-usuarios-rol')?.addEventListener('change', filtrarUsuarios);
  document.getElementById('btn-limpiar-filtros-usuarios')?.addEventListener('click', () => {
    document.getElementById('filtro-usuarios-query').value = '';
    document.getElementById('filtro-usuarios-rol').value = '';
    filtrarUsuarios();
  });

  // Divisas
  document.getElementById('form-divisas-convertir')?.addEventListener('submit', convertirMontoDivisas);

  // Visor JSON
  document.getElementById('btn-copiar-visor')?.addEventListener('click', () => {
    copiarTexto(document.getElementById('visor-json-content').innerText, 'Factura JSON copiada al portapapeles');
  });
  document.getElementById('btn-descargar-json')?.addEventListener('click', descargarFacturaJSON);

  // Modal destructivo unificado
  document.getElementById('btn-ejecutar-confirmacion')?.addEventListener('click', ejecutarConfirmacionDestructiva);
  document.getElementById('btn-cancelar-confirmacion')?.addEventListener('click', () => {
    cerrarModal('modal-confirmar-accion');
    AppState.accionConfirmacion = null;
  });
}

function configurarNavegacionPorTeclado() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.editorial-modal-backdrop.open').forEach(m => {
        cerrarModal(m.id);
      });
    }
  });
}

function cambiarPestana(tabId, clickedBtn) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
  });

  const pane = document.getElementById(tabId);
  if (pane) {
    pane.classList.remove('hidden');
    pane.classList.add('active');
  }
  if (clickedBtn) {
    clickedBtn.classList.add('active');
    clickedBtn.setAttribute('aria-selected', 'true');
  }

  // Cargar datos correspondientes si es necesario
  if (tabId === 'tab-dashboard') {
    cargarDashboard();
  }
}

// ==============================================================================
// CARGA GLOBAL DE DATOS
// ==============================================================================

async function cargarTodo() {
  const promesas = [cargarPagos(), cargarFacturas(), cargarDashboard()];
  if (AppState.usuarioActual?.rol === 'admin') {
    promesas.push(cargarUsuarios());
  }
  await Promise.all(promesas);
}

// ==============================================================================
// SECCIÓN 01: DASHBOARD ANALÍTICO DEL SISTEMA (UI03 + REPORTES)
// ==============================================================================

async function cargarDashboard() {
  if (!AppState.token) return;

  const estado = document.getElementById('dashboard-estado');
  if (estado) {
    estado.className = 'api-status';
    estado.innerHTML = '<span class="spinner"></span> Actualizando métricas del sistema...';
  }

  const res = await apiFetch('/api/reportes/resumen');
  if (!res.ok) {
    if (estado) {
      estado.className = 'api-status error';
      estado.textContent = res.data?.error || 'No se pudieron consultar los reportes del dashboard.';
    }
    return;
  }

  const { pagos, facturas } = res.data;

  // Actualizar Tarjetas KPI
  document.getElementById('dash-total-transacciones').textContent = String(pagos?.total_transacciones ?? 0);
  document.getElementById('dash-monto-total').textContent = formatearMontosPorMoneda(
    Object.fromEntries(
      Object.entries(pagos?.por_moneda || {}).map(([moneda, datos]) => [moneda, datos.monto])
    )
  );

  document.getElementById('dash-total-facturas').textContent = String(facturas?.total_facturas ?? 0);
  document.getElementById('dash-total-iva').textContent = formatearMontosPorMoneda(
    Object.fromEntries(
      Object.entries(facturas?.por_moneda || {}).map(([moneda, datos]) => [moneda, datos.iva])
    )
  );

  // Tablas analíticas
  renderizarTablaConteos(pagos?.por_estado, 'dash-por-estado');
  renderizarTablaConteos(pagos?.por_metodo, 'dash-por-metodo');
  renderizarTablaMonedas(pagos?.por_moneda, 'dash-por-moneda');
  renderizarTablaFacturasMoneda(facturas?.por_moneda, 'dash-facturas-por-moneda');
  renderizarTopClientes(facturas?.top_clientes, 'dash-top-clientes');

  if (estado) {
    const ahora = new Date().toLocaleTimeString('es-CO');
    estado.textContent = `Dashboard actualizado a las ${ahora}.`;
  }
}

function renderizarTablaConteos(datos, idTbody) {
  const tbody = document.getElementById(idTbody);
  if (!tbody) return;
  const filas = Object.entries(datos || {});
  tbody.innerHTML = filas.length
    ? filas.map(([nombre, cantidad]) => `
      <tr>
        <td><strong>${escaparHTML(nombre.toUpperCase())}</strong></td>
        <td class="text-right"><strong>${escaparHTML(String(cantidad ?? 0))}</strong></td>
      </tr>
    `).join('')
    : '<tr><td colspan="2" class="text-center py-4 text-muted">Sin datos</td></tr>';
}

function renderizarTablaMonedas(datos, idTbody) {
  const tbody = document.getElementById(idTbody);
  if (!tbody) return;
  const filas = Object.entries(datos || {});
  tbody.innerHTML = filas.length
    ? filas.map(([moneda, detalle]) => `
      <tr>
        <td><strong>${escaparHTML(moneda)}</strong></td>
        <td class="text-right">${escaparHTML(String(detalle.cantidad ?? 0))}</td>
        <td class="text-right"><strong>${formatearMoneda(detalle.monto, moneda)}</strong></td>
      </tr>
    `).join('')
    : '<tr><td colspan="3" class="text-center py-4 text-muted">Sin datos</td></tr>';
}

function renderizarTablaFacturasMoneda(datos, idTbody) {
  const tbody = document.getElementById(idTbody);
  if (!tbody) return;
  const filas = Object.entries(datos || {});
  tbody.innerHTML = filas.length
    ? filas.map(([moneda, resumen]) => `
      <tr>
        <td><strong>${escaparHTML(moneda)}</strong></td>
        <td class="text-right"><strong>${formatearMoneda(resumen.total_facturado, moneda)}</strong></td>
        <td class="text-right">${formatearMoneda(resumen.iva, moneda)}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="3" class="text-center py-4 text-muted">Sin datos</td></tr>';
}

function renderizarTopClientes(clientes, idTbody) {
  const tbody = document.getElementById(idTbody);
  if (!tbody) return;
  tbody.innerHTML = Array.isArray(clientes) && clientes.length
    ? clientes.map(cliente => `
      <tr>
        <td><strong>${escaparHTML(cliente.cliente)}</strong> <span class="mono text-xs">(${escaparHTML(cliente.moneda)})</span></td>
        <td class="text-right"><strong>${formatearMoneda(cliente.total, cliente.moneda)}</strong></td>
      </tr>
    `).join('')
    : '<tr><td colspan="2" class="text-center py-4 text-muted">Sin datos disponibles</td></tr>';
}

// ==============================================================================
// SECCIÓN 02: GESTIÓN DE PAGOS (CRUD Y ACCIÓN DESTRUCTIVA - UI02)
// ==============================================================================

async function cargarPagos() {
  if (!AppState.token) return;
  const tbody = document.getElementById('tbody-pagos');
  if (tbody && AppState.pagos.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="table-loading-box"><span class="spinner"></span> Cargando transacciones...</td></tr>`;
  }

  const res = await apiFetch('/pagos');
  if (res.ok && Array.isArray(res.data)) {
    AppState.pagos = res.data;
    renderizarTablaPagos(AppState.pagos);
    actualizarSelectorPagosEnFacturas(AppState.pagos);
  }
}

function renderizarTablaPagos(pagos) {
  const tbody = document.getElementById('tbody-pagos');
  const countBadge = document.getElementById('count-pagos');
  const esAdmin = AppState.usuarioActual?.rol === 'admin';

  if (countBadge) countBadge.textContent = pagos.length;
  if (!tbody) return;

  if (pagos.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8">
          <div class="table-empty-box">
            <h3 class="table-empty-title">NO HAY PAGOS REGISTRADOS</h3>
            <p class="table-empty-desc">No se encontraron pagos con los criterios actuales de búsqueda.</p>
            <button type="button" class="btn-outline btn-xs" onclick="abrirModalNuevoPago()">+ REGISTRAR PAGO AHORA</button>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = pagos.map(p => `
    <tr>
      <td><strong>#${p.id}</strong></td>
      <td><strong>${escaparHTML(p.cliente)}</strong></td>
      <td><strong>${formatearMoneda(p.monto, p.moneda)}</strong></td>
      <td><span class="mono">${escaparHTML(p.metodo_pago.toUpperCase())}</span></td>
      <td><span class="status-pill ${p.estado}">${escaparHTML(p.estado.toUpperCase())}</span></td>
      <td><span class="mono">${escaparHTML(p.creado_por || 'sistema')}</span></td>
      <td><span class="mono text-xs">${escaparHTML(p.fecha_creacion || '')}</span></td>
      <td class="text-right">
        <div class="table-actions">
          <button type="button" class="btn-table-action" onclick="verDetallePago(${p.id})">
            DETALLE
          </button>
          <button type="button" class="btn-table-action" onclick="iniciarFacturacionDePago(${p.id})">
            + FACTURAR
          </button>
          ${esAdmin ? `
            <button type="button" class="btn-table-action" onclick="iniciarEdicionPago(${p.id})">
              EDITAR
            </button>
            <button type="button" class="btn-table-action delete" onclick="confirmarEliminarPago(${p.id})">
              ELIMINAR
            </button>
          ` : ''}
        </div>
      </td>
    </tr>
  `).join('');
}

function filtrarPagos() {
  const query = (document.getElementById('filtro-pagos-cliente')?.value || '').toLowerCase().trim();
  const estado = document.getElementById('filtro-pagos-estado')?.value || '';
  const metodo = document.getElementById('filtro-pagos-metodo')?.value || '';

  const filtrados = AppState.pagos.filter(p => {
    const matchQ = !query || p.cliente.toLowerCase().includes(query);
    const matchE = !estado || p.estado === estado;
    const matchM = !metodo || p.metodo_pago === metodo;
    return matchQ && matchE && matchM;
  });

  renderizarTablaPagos(filtrados);
}

function abrirModalNuevoPago() {
  AppState.pagoEnEdicionId = null;
  document.getElementById('form-nuevo-pago')?.reset();
  document.getElementById('titulo-modal-pago').textContent = 'NUEVO PAGO SIMULADO';
  document.getElementById('btn-submit-pago').textContent = 'REGISTRAR PAGO →';
  abrirModal('modal-pago');
}

function iniciarEdicionPago(pagoId) {
  if (AppState.usuarioActual?.rol !== 'admin') {
    lanzarToast('forbidden', '403 FORBIDDEN', 'Solo un administrador puede modificar pagos.');
    return;
  }

  const pago = AppState.pagos.find(p => p.id === pagoId);
  if (!pago) {
    lanzarToast('error', 'NO ENCONTRADO', 'No se encontró el pago para editar.');
    return;
  }

  AppState.pagoEnEdicionId = pagoId;
  document.getElementById('pago-cliente').value = pago.cliente;
  document.getElementById('pago-monto').value = pago.monto;
  document.getElementById('pago-moneda').value = pago.moneda;
  document.getElementById('pago-metodo').value = pago.metodo_pago;
  document.getElementById('pago-estado').value = pago.estado;

  document.getElementById('titulo-modal-pago').textContent = `EDITAR PAGO #${pagoId}`;
  document.getElementById('btn-submit-pago').textContent = 'GUARDAR CAMBIOS →';
  abrirModal('modal-pago');
}

async function guardarPago(e) {
  e.preventDefault();
  const pagoId = AppState.pagoEnEdicionId;
  const payload = {
    cliente: document.getElementById('pago-cliente').value.trim(),
    monto: parseFloat(document.getElementById('pago-monto').value),
    moneda: document.getElementById('pago-moneda').value,
    metodo_pago: document.getElementById('pago-metodo').value,
    estado: document.getElementById('pago-estado').value
  };

  const btnSubmit = document.getElementById('btn-submit-pago');
  btnSubmit.disabled = true;

  const url = pagoId ? `/pagos/${pagoId}` : '/pagos';
  const method = pagoId ? 'PUT' : 'POST';

  const res = await apiFetch(url, { method, body: JSON.stringify(payload) });
  btnSubmit.disabled = false;

  if (res.ok && res.data) {
    cerrarModal('modal-pago');
    AppState.pagoEnEdicionId = null;
    lanzarToast(
      'success',
      pagoId ? 'PAGO ACTUALIZADO' : 'PAGO REGISTRADO',
      pagoId ? `Pago #${res.data.id} actualizado correctamente.` : `Pago #${res.data.id} creado con éxito para ${res.data.cliente}.`
    );
    await cargarPagos();
    await cargarDashboard();
  } else {
    lanzarToast('error', 'ERROR EN PAGO', res.data?.error || 'No se pudo guardar el pago.');
  }
}

function verDetallePago(pagoId) {
  const pago = AppState.pagos.find(p => p.id === pagoId);
  if (!pago) return;

  const contenedor = document.getElementById('contenedor-detalle-pago');
  contenedor.innerHTML = `
    <div class="detail-item">
      <span class="detail-label">IDENTIFICADOR DE PAGO</span>
      <span class="detail-value">#${pago.id}</span>
    </div>
    <div class="detail-item">
      <span class="detail-label">ESTADO TRANSACCIONAL</span>
      <span class="detail-value"><span class="status-pill ${pago.estado}">${escaparHTML(pago.estado.toUpperCase())}</span></span>
    </div>
    <div class="detail-item full-width">
      <span class="detail-label">CLIENTE / TITULAR</span>
      <span class="detail-value">${escaparHTML(pago.cliente)}</span>
    </div>
    <div class="detail-item">
      <span class="detail-label">MONTO TOTAL</span>
      <span class="detail-value">${formatearMoneda(pago.monto, pago.moneda)}</span>
    </div>
    <div class="detail-item">
      <span class="detail-label">DIVISA ASIGNADA</span>
      <span class="detail-value">${escaparHTML(pago.moneda)}</span>
    </div>
    <div class="detail-item">
      <span class="detail-label">MÉTODO DE PAGO</span>
      <span class="detail-value mono">${escaparHTML(pago.metodo_pago.toUpperCase())}</span>
    </div>
    <div class="detail-item">
      <span class="detail-label">REGISTRADO POR</span>
      <span class="detail-value mono">${escaparHTML(pago.creado_por || 'sistema')}</span>
    </div>
    <div class="detail-item full-width">
      <span class="detail-label">FECHA Y HORA DE CREACIÓN</span>
      <span class="detail-value mono">${escaparHTML(pago.fecha_creacion || '')}</span>
    </div>
  `;
  abrirModal('modal-detalle-pago');
}

function confirmarEliminarPago(pagoId) {
  const pago = AppState.pagos.find(p => p.id === pagoId);
  if (!pago) return;

  solicitarConfirmacionDestructiva({
    titulo: 'ELIMINAR PAGO DEL SISTEMA',
    mensaje: `¿Estás seguro de que deseas eliminar permanentemente este pago?`,
    itemInfo: `<strong>Pago #${pago.id}</strong> — Cliente: ${escaparHTML(pago.cliente)} | Monto: ${formatearMoneda(pago.monto, pago.moneda)}`,
    ejecutar: async () => {
      const res = await apiFetch(`/pagos/${pagoId}`, { method: 'DELETE' });
      if (res.ok) {
        lanzarToast('success', 'PAGO ELIMINADO', res.data?.mensaje || `Pago #${pagoId} borrado con éxito.`);
        await cargarPagos();
        await cargarDashboard();
      } else {
        lanzarToast('error', 'ERROR AL ELIMINAR', res.data?.error || 'No se pudo eliminar el pago.');
      }
    }
  });
}

// ==============================================================================
// SECCIÓN 03: FACTURACIÓN EN FORMATO JSON CON FIRMA SHA-256 (UI02 + UI03)
// ==============================================================================

async function cargarFacturas() {
  if (!AppState.token) return;
  const tbody = document.getElementById('tbody-facturas');
  if (tbody && AppState.facturas.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="table-loading-box"><span class="spinner"></span> Cargando facturas JSON...</td></tr>`;
  }

  const res = await apiFetch('/facturas');
  if (res.ok && Array.isArray(res.data)) {
    AppState.facturas = res.data;
    renderizarTablaFacturas(AppState.facturas);
  }
}

function renderizarTablaFacturas(facturas) {
  const tbody = document.getElementById('tbody-facturas');
  const countBadge = document.getElementById('count-facturas');
  const esAdmin = AppState.usuarioActual?.rol === 'admin';

  if (countBadge) countBadge.textContent = facturas.length;
  if (!tbody) return;

  if (facturas.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9">
          <div class="table-empty-box">
            <h3 class="table-empty-title">NO HAY FACTURAS EMITIDAS</h3>
            <p class="table-empty-desc">No se han emitido facturas en formato JSON con los filtros actuales.</p>
            <button type="button" class="btn-outline btn-xs" onclick="abrirModalFactura()">+ EMITIR FACTURA AHORA</button>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = facturas.map(f => `
    <tr>
      <td><strong>${escaparHTML(f.numero_factura)}</strong></td>
      <td>
        <strong>${escaparHTML(f.cliente)}</strong>
        <div class="mono text-xs text-muted">${escaparHTML(f.email_cliente || '')}</div>
      </td>
      <td><span class="mono">${escaparHTML(f.documento_cliente || 'N/A')}</span></td>
      <td>
        ${f.pago_id ? `<span class="mono">#${f.pago_id}</span>` : `<span class="mono text-muted">DIRECTA</span>`}
      </td>
      <td><span class="mono">${formatearMoneda(f.subtotal, f.moneda)}</span></td>
      <td><span class="mono">${formatearMoneda(f.impuesto, f.moneda)}</span></td>
      <td><strong class="mono">${formatearMoneda(f.total, f.moneda)}</strong></td>
      <td><span class="status-pill ${f.estado}">${escaparHTML(f.estado.toUpperCase())}</span></td>
      <td class="text-right">
        <div class="table-actions">
          <button type="button" class="btn-table-action" onclick="verFacturaFormatoEstandar(${f.id})">
            VER JSON
          </button>
          ${esAdmin && f.estado === 'emitida' ? `
            <button type="button" class="btn-table-action delete" onclick="confirmarAnularFactura(${f.id})">
              ANULAR
            </button>
          ` : ''}
        </div>
      </td>
    </tr>
  `).join('');
}

function filtrarFacturas() {
  const query = (document.getElementById('filtro-facturas-query')?.value || '').toLowerCase().trim();
  const estado = document.getElementById('filtro-facturas-estado')?.value || '';

  const filtrados = AppState.facturas.filter(f => {
    const matchQ = !query ||
      f.cliente.toLowerCase().includes(query) ||
      f.numero_factura.toLowerCase().includes(query);
    const matchE = !estado || f.estado === estado;
    return matchQ && matchE;
  });

  renderizarTablaFacturas(filtrados);
}

function abrirModalFactura() {
  document.getElementById('form-nueva-factura')?.reset();
  const radioPago = document.getElementById('radio-factura-pago');
  if (radioPago) radioPago.checked = true;
  alternarModoFactura();

  if (AppState.pagoSeleccionadoParaFacturar) {
    const selectPago = document.getElementById('factura-pago-id');
    if (selectPago) selectPago.value = AppState.pagoSeleccionadoParaFacturar;
    alSeleccionarPagoEnFactura();
    AppState.pagoSeleccionadoParaFacturar = null;
  }

  abrirModal('modal-factura');
}

function alternarModoFactura() {
  const modo = document.querySelector('input[name="modo-factura"]:checked')?.value || 'pago';
  const grupoPago = document.getElementById('grupo-selector-pago');
  const seccionItems = document.getElementById('seccion-items-factura');
  const esManual = modo === 'manual';
  const campoCliente = document.getElementById('factura-cliente');
  const camposItems = document.querySelectorAll('#items-container input');

  if (campoCliente) campoCliente.required = esManual;
  camposItems.forEach(campo => {
    campo.disabled = !esManual;
  });

  if (!esManual) {
    grupoPago?.classList.remove('hidden');
    seccionItems?.classList.add('hidden');
    alSeleccionarPagoEnFactura();
  } else {
    grupoPago?.classList.add('hidden');
    seccionItems?.classList.remove('hidden');

    const container = document.getElementById('items-container');
    if (container && container.children.length === 0) {
      agregarFilaItemFactura('Servicio o producto estándar', 1, 100);
    }
    recalcularTotalesFactura();
  }
}

function actualizarSelectorPagosEnFacturas(pagos) {
  const select = document.getElementById('factura-pago-id');
  if (!select) return;

  select.innerHTML = '<option value="">Selecciona un pago registrado...</option>' +
    pagos.map(p => `
      <option value="${p.id}" data-cliente="${escaparHTML(p.cliente)}" data-monto="${p.monto}" data-moneda="${p.moneda}">
        Pago #${p.id} — ${escaparHTML(p.cliente)} (${formatearMoneda(p.monto, p.moneda)}) [${p.estado.toUpperCase()}]
      </option>
    `).join('');
}

function alSeleccionarPagoEnFactura() {
  const select = document.getElementById('factura-pago-id');
  if (!select) return;
  const opt = select.options[select.selectedIndex];

  if (!opt || !opt.value) {
    document.getElementById('factura-cliente').value = '';
    document.getElementById('prev-subtotal').textContent = '$0.00';
    document.getElementById('prev-iva').textContent = '$0.00';
    document.getElementById('prev-total').textContent = '$0.00';
    return;
  }

  const cliente = opt.getAttribute('data-cliente') || '';
  const monto = parseFloat(opt.getAttribute('data-monto')) || 0;
  const moneda = opt.getAttribute('data-moneda') || 'COP';

  document.getElementById('factura-cliente').value = cliente;
  document.getElementById('factura-moneda').value = moneda;

  const tasa = parseFloat(document.getElementById('factura-iva-porcentaje').value) || 0;
  const iva = monto * (tasa / 100);
  const total = monto + iva;

  document.getElementById('prev-subtotal').textContent = formatearMoneda(monto, moneda);
  document.getElementById('prev-iva-tasa').textContent = tasa.toFixed(1);
  document.getElementById('prev-iva').textContent = formatearMoneda(iva, moneda);
  document.getElementById('prev-total').textContent = formatearMoneda(total, moneda);
}

function agregarFilaItemFactura(desc = '', cant = 1, precio = 0) {
  const container = document.getElementById('items-container');
  if (!container) return;
  const row = document.createElement('div');
  row.className = 'item-row';
  row.innerHTML = `
    <input type="text" class="item-desc" placeholder="Descripción del cobro" value="${escaparHTML(desc)}" required>
    <input type="number" class="item-cant" placeholder="Cant." value="${cant}" min="1" step="1" required>
    <input type="number" class="item-precio" placeholder="Precio unit." value="${precio}" min="0.01" step="0.01" required>
    <button type="button" class="btn-remove-row" title="Eliminar fila">&times;</button>
  `;

  row.querySelectorAll('input').forEach(input => {
    input.addEventListener('input', recalcularTotalesFactura);
  });

  row.querySelector('.btn-remove-row')?.addEventListener('click', () => {
    if (container.children.length > 1) {
      row.remove();
      recalcularTotalesFactura();
    } else {
      lanzarToast('info', 'REQUERIMIENTO', 'La factura debe tener al menos una línea de ítem.');
    }
  });

  container.appendChild(row);
  recalcularTotalesFactura();
}

function recalcularTotalesFactura() {
  const modo = document.querySelector('input[name="modo-factura"]:checked')?.value || 'pago';
  if (modo === 'pago') {
    alSeleccionarPagoEnFactura();
    return;
  }

  const container = document.getElementById('items-container');
  if (!container) return;
  let subtotal = 0;

  Array.from(container.children).forEach(row => {
    const cant = parseFloat(row.querySelector('.item-cant')?.value) || 0;
    const precio = parseFloat(row.querySelector('.item-precio')?.value) || 0;
    subtotal += (cant * precio);
  });

  const moneda = document.getElementById('factura-moneda')?.value || 'COP';
  const tasa = parseFloat(document.getElementById('factura-iva-porcentaje')?.value) || 0;
  const iva = subtotal * (tasa / 100);
  const total = subtotal + iva;

  document.getElementById('prev-subtotal').textContent = formatearMoneda(subtotal, moneda);
  document.getElementById('prev-iva-tasa').textContent = tasa.toFixed(1);
  document.getElementById('prev-iva').textContent = formatearMoneda(iva, moneda);
  document.getElementById('prev-total').textContent = formatearMoneda(total, moneda);
}

function iniciarFacturacionDePago(pagoId) {
  AppState.pagoSeleccionadoParaFacturar = pagoId;
  cambiarPestana('tab-facturas', document.getElementById('tab-btn-facturas'));
  abrirModalFactura();
}

async function guardarNuevaFactura(e) {
  e.preventDefault();
  const modo = document.querySelector('input[name="modo-factura"]:checked')?.value || 'pago';

  const payload = {
    cliente: document.getElementById('factura-cliente').value.trim(),
    email_cliente: document.getElementById('factura-email').value.trim() || null,
    documento_cliente: document.getElementById('factura-documento').value.trim() || null,
    moneda: document.getElementById('factura-moneda').value,
    porcentaje_impuesto: parseFloat(document.getElementById('factura-iva-porcentaje').value) || 0
  };

  if (modo === 'pago') {
    const pId = document.getElementById('factura-pago-id').value;
    if (!pId) {
      lanzarToast('error', 'SELECCIÓN VACÍA', 'Debes elegir un pago de la lista.');
      return;
    }
    payload.pago_id = Number.parseInt(pId, 10);
  } else {
    const items = [];
    const container = document.getElementById('items-container');
    if (container) {
      Array.from(container.children).forEach(row => {
        const desc = row.querySelector('.item-desc')?.value.trim();
        const cant = Number.parseFloat(row.querySelector('.item-cant')?.value);
        const precio = Number.parseFloat(row.querySelector('.item-precio')?.value);
        if (desc && Number.isFinite(cant) && Number.isFinite(precio)) {
          items.push({ descripcion: desc, cantidad: cant, precio_unitario: precio });
        }
      });
    }

    if (items.length === 0) {
      lanzarToast('error', 'SIN ARTÍCULOS', 'Agrega al menos una línea válida a la factura.');
      return;
    }
    payload.items = items;
  }

  const btnSubmit = document.getElementById('btn-submit-factura');
  btnSubmit.disabled = true;

  const res = await apiFetch('/facturas', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  btnSubmit.disabled = false;

  if (res.ok && res.data) {
    cerrarModal('modal-factura');
    lanzarToast('success', 'FACTURA EMITIDA', `Factura #${res.data.numero_factura} emitida en formato JSON.`);
    await cargarFacturas();
    await cargarDashboard();
    // Abrir de inmediato el visor oficial para ver los efectos y la firma SHA-256 (UI03)
    verFacturaFormatoEstandar(res.data.id);
  } else {
    lanzarToast('error', 'ERROR EN FACTURA', res.data?.error || 'No se pudo emitir la factura.');
  }
}

async function verFacturaFormatoEstandar(facturaId) {
  const res = await apiFetch(`/facturas/${facturaId}/json`);
  if (!res.ok || !res.data) {
    lanzarToast('error', 'ERROR VISOR', res.data?.error || 'No se pudo cargar el JSON de la factura.');
    return;
  }

  const data = res.data;
  document.getElementById('visor-numero-factura').textContent = `FACTURA #${data.encabezado.numero_factura}`;
  document.getElementById('visor-tipo-doc').textContent =
    `${data.encabezado.tipo_documento.toUpperCase()} // FIRMA SHA-256 VERIFICADA`;

  const codeEl = document.getElementById('visor-json-content');
  if (codeEl) {
    codeEl.innerHTML = colorearSintaxisJSON(JSON.stringify(data, null, 2));
  }

  abrirModal('modal-visor-json');
}

function confirmarAnularFactura(facturaId) {
  const factura = AppState.facturas.find(f => f.id === facturaId);
  if (!factura) return;

  solicitarConfirmacionDestructiva({
    titulo: 'ANULAR FACTURA EN FORMATO JSON',
    mensaje: `¿Estás seguro de anular esta factura emitida? El registro contable se conservará para auditoría con estado ANULADA.`,
    itemInfo: `<strong>Factura ${escaparHTML(factura.numero_factura)}</strong> — Cliente: ${escaparHTML(factura.cliente)} | Total: ${formatearMoneda(factura.total, factura.moneda)}`,
    ejecutar: async () => {
      const res = await apiFetch(`/facturas/${facturaId}`, { method: 'DELETE' });
      if (res.ok) {
        lanzarToast('success', 'FACTURA ANULADA', res.data?.mensaje || `Factura #${facturaId} anulada.`);
        await cargarFacturas();
        await cargarDashboard();
      } else {
        lanzarToast('error', 'ERROR AL ANULAR', res.data?.error || 'No se pudo anular la factura.');
      }
    }
  });
}

function descargarFacturaJSON() {
  const content = document.getElementById('visor-json-content')?.innerText || '';
  if (!content) return;
  const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `factura_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
  lanzarToast('info', 'DESCARGA COMPLETADA', 'Documento JSON descargado en tu dispositivo.');
}

// ==============================================================================
// SECCIÓN 04: CRUD DE USUARIOS (EXCLUSIVO ADMINISTRADOR - REEMPLAZO DE ROLES)
// ==============================================================================

async function cargarUsuarios() {
  if (!AppState.token || AppState.usuarioActual?.rol !== 'admin') return;
  const tbody = document.getElementById('tbody-usuarios');
  if (tbody && AppState.usuarios.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="table-loading-box"><span class="spinner"></span> Cargando directorio de usuarios...</td></tr>`;
  }

  const res = await apiFetch('/usuarios');
  if (res.ok && Array.isArray(res.data)) {
    AppState.usuarios = res.data;
    renderizarTablaUsuarios(AppState.usuarios);
  }
}

function renderizarTablaUsuarios(usuarios) {
  const tbody = document.getElementById('tbody-usuarios');
  const countBadge = document.getElementById('count-usuarios');
  if (countBadge) countBadge.textContent = usuarios.length;
  if (!tbody) return;

  if (usuarios.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6">
          <div class="table-empty-box">
            <h3 class="table-empty-title">NO HAY USUARIOS</h3>
            <p class="table-empty-desc">No se encontraron usuarios con los criterios de búsqueda actuales.</p>
            <button type="button" class="btn-outline btn-xs" onclick="abrirModalNuevoUsuario()">+ CREAR USUARIO AHORA</button>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  const currentUser = AppState.usuarioActual?.username;

  tbody.innerHTML = usuarios.map(u => {
    const esPropio = u.username === currentUser;
    return `
      <tr>
        <td><strong>#${u.id}</strong></td>
        <td>
          <strong>${escaparHTML(u.username)}</strong>
          ${esPropio ? ' <span class="badge-tag text-xs">(SESIÓN ACTUAL)</span>' : ''}
        </td>
        <td>
          <span class="user-role-tag ${u.rol}">
            ${escaparHTML(u.rol.toUpperCase())}
          </span>
        </td>
        <td><span class="mono">${escaparHTML(u.email || 'N/A')}</span></td>
        <td><span class="mono text-xs">${escaparHTML(u.fecha_creacion || '')}</span></td>
        <td class="text-right">
          <div class="table-actions">
            <button type="button" class="btn-table-action" onclick="verDetalleUsuario(${u.id})">
              DETALLE
            </button>
            <button type="button" class="btn-table-action" onclick="iniciarEdicionUsuario(${u.id})">
              EDITAR
            </button>
            ${!esPropio ? `
              <button type="button" class="btn-table-action delete" onclick="confirmarEliminarUsuario(${u.id})">
                ELIMINAR
              </button>
            ` : `
              <span class="text-muted text-xs mono p-1" title="No puedes eliminar tu propia cuenta en sesión">PROTEGIDO</span>
            `}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function filtrarUsuarios() {
  const query = (document.getElementById('filtro-usuarios-query')?.value || '').toLowerCase().trim();
  const rol = document.getElementById('filtro-usuarios-rol')?.value || '';

  const filtrados = AppState.usuarios.filter(u => {
    const matchQ = !query ||
      u.username.toLowerCase().includes(query) ||
      (u.email && u.email.toLowerCase().includes(query));
    const matchR = !rol || u.rol === rol;
    return matchQ && matchR;
  });

  renderizarTablaUsuarios(filtrados);
}

function abrirModalNuevoUsuario() {
  document.getElementById('form-nuevo-usuario')?.reset();
  abrirModal('modal-usuario');
}

async function guardarNuevoUsuarioAdmin(e) {
  e.preventDefault();
  const payload = {
    username: document.getElementById('nuevo-usuario-username').value.trim(),
    password: document.getElementById('nuevo-usuario-password').value,
    email: document.getElementById('nuevo-usuario-email').value.trim() || null,
    rol: document.getElementById('nuevo-usuario-rol').value
  };

  const btnSubmit = document.getElementById('btn-submit-usuario');
  btnSubmit.disabled = true;

  const res = await apiFetch('/usuarios', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  btnSubmit.disabled = false;

  if (res.ok && res.data) {
    cerrarModal('modal-usuario');
    lanzarToast('success', 'USUARIO CREADO', `Cuenta '${res.data.username}' creada exitosamente con rol ${res.data.rol.toUpperCase()}.`);
    await cargarUsuarios();
  } else {
    lanzarToast('error', 'ERROR AL CREAR USUARIO', res.data?.error || 'No se pudo crear el usuario.');
  }
}

function iniciarEdicionUsuario(usuarioId) {
  const usuario = AppState.usuarios.find(u => u.id === usuarioId);
  if (!usuario) return;

  document.getElementById('editar-usuario-id').value = usuario.id;
  document.getElementById('editar-usuario-username').value = usuario.username;
  document.getElementById('editar-usuario-email').value = usuario.email || '';
  document.getElementById('editar-usuario-password').value = '';

  const selectRol = document.getElementById('editar-usuario-rol');
  const avisoRol = document.getElementById('editar-usuario-rol-aviso');
  selectRol.value = usuario.rol;

  // Si es el usuario actual, advertir que no puede quitarse su propio rol de admin
  if (usuario.username === AppState.usuarioActual?.username) {
    selectRol.disabled = true;
    avisoRol.textContent = 'No puedes revocar tu propio rol de administrador.';
  } else {
    selectRol.disabled = false;
    avisoRol.textContent = '';
  }

  abrirModal('modal-editar-usuario');
}

async function guardarEdicionUsuario(e) {
  e.preventDefault();
  const usuarioId = document.getElementById('editar-usuario-id').value;
  const selectRol = document.getElementById('editar-usuario-rol');

  const payload = {
    email: document.getElementById('editar-usuario-email').value.trim() || null,
    rol: selectRol.value
  };

  const pass = document.getElementById('editar-usuario-password').value;
  if (pass) {
    payload.password = pass;
  }

  const btnSubmit = document.getElementById('btn-submit-editar-usuario');
  btnSubmit.disabled = true;

  const res = await apiFetch(`/usuarios/${usuarioId}`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
  btnSubmit.disabled = false;

  if (res.ok && res.data) {
    cerrarModal('modal-editar-usuario');
    lanzarToast('success', 'USUARIO ACTUALIZADO', `Cuenta '${res.data.username}' actualizada correctamente.`);
    await cargarUsuarios();
  } else {
    lanzarToast('error', 'ERROR AL EDITAR', res.data?.error || 'No se pudieron guardar los cambios.');
  }
}

function verDetalleUsuario(usuarioId) {
  const u = AppState.usuarios.find(user => user.id === usuarioId);
  if (!u) return;

  const contenedor = document.getElementById('contenedor-detalle-usuario');
  contenedor.innerHTML = `
    <div class="detail-item">
      <span class="detail-label">ID DE USUARIO</span>
      <span class="detail-value">#${u.id}</span>
    </div>
    <div class="detail-item">
      <span class="detail-label">ROL ASIGNADO</span>
      <span class="detail-value"><span class="user-role-tag ${u.rol}">${escaparHTML(u.rol.toUpperCase())}</span></span>
    </div>
    <div class="detail-item full-width">
      <span class="detail-label">NOMBRE DE USUARIO</span>
      <span class="detail-value">${escaparHTML(u.username)}</span>
    </div>
    <div class="detail-item full-width">
      <span class="detail-label">CORREO ELECTRÓNICO</span>
      <span class="detail-value">${escaparHTML(u.email || 'No registrado')}</span>
    </div>
    <div class="detail-item full-width">
      <span class="detail-label">FECHA DE REGISTRO</span>
      <span class="detail-value mono">${escaparHTML(u.fecha_creacion || '')}</span>
    </div>
  `;
  abrirModal('modal-detalle-usuario');
}

function confirmarEliminarUsuario(usuarioId) {
  const usuario = AppState.usuarios.find(u => u.id === usuarioId);
  if (!usuario) return;

  if (usuario.username === AppState.usuarioActual?.username) {
    lanzarToast('error', 'OPERACIÓN DENEGADA', 'No puedes eliminar tu propia cuenta en sesión activa.');
    return;
  }

  solicitarConfirmacionDestructiva({
    titulo: 'ELIMINAR USUARIO DEL SISTEMA',
    mensaje: `¿Estás seguro de que deseas eliminar permanentemente la cuenta de este usuario? Se revocarán todos sus accesos.`,
    itemInfo: `<strong>Usuario #${usuario.id}: ${escaparHTML(usuario.username)}</strong> (Rol: ${usuario.rol.toUpperCase()})`,
    ejecutar: async () => {
      const res = await apiFetch(`/usuarios/${usuarioId}`, { method: 'DELETE' });
      if (res.ok) {
        lanzarToast('success', 'USUARIO ELIMINADO', res.data?.mensaje || `Usuario eliminado.`);
        await cargarUsuarios();
      } else {
        lanzarToast('error', 'ERROR AL ELIMINAR', res.data?.error || 'No se pudo eliminar el usuario.');
      }
    }
  });
}

// ==============================================================================
// SECCIÓN 05: CONVERSIÓN DE MONEDA EN VIVO (UI03 FUNCIÓN ESPECIAL)
// ==============================================================================

async function convertirMontoDivisas(e) {
  e.preventDefault();
  const estado = document.getElementById('divisas-estado');
  const btnSubmit = document.getElementById('btn-convertir-divisas');

  const monto = document.getElementById('divisas-monto')?.value;
  const de = document.getElementById('divisas-de')?.value;
  const a = document.getElementById('divisas-a')?.value;

  if (estado) {
    estado.className = 'api-status';
    estado.innerHTML = '<span class="spinner"></span> Consultando tasas oficiales y calculando...';
  }
  if (btnSubmit) btnSubmit.disabled = true;

  const res = await apiFetch(`/divisas/convertir?monto=${encodeURIComponent(monto)}&de=${de}&a=${a}`);
  if (btnSubmit) btnSubmit.disabled = false;

  if (!res.ok || !res.data) {
    if (estado) {
      estado.className = 'api-status error';
      estado.textContent = res.data?.error || 'No se pudo realizar la conversión.';
    }
    return;
  }

  const data = res.data;
  const fuenteTexto = data.fuente === 'respaldo_local'
    ? 'Respaldo local (tasas estimadas de contingencia)'
    : 'Proveedor en vivo (open.er-api.com)';

  document.getElementById('divisas-resultado').textContent =
    `${formatearMoneda(data.resultado, data.a)} ${data.a}`;
  document.getElementById('divisas-tasa').textContent =
    `Tasa aplicada: 1 ${data.de} = ${formatearNumero(data.tasa)} ${data.a}`;
  document.getElementById('divisas-fuente').textContent = `Fuente de datos: ${fuenteTexto}`;
  document.getElementById('divisas-fecha').textContent =
    `Última actualización: ${data.fecha_actualizacion}`;

  if (estado) {
    estado.className = 'api-status';
    estado.textContent = 'Conversión calculada exitosamente.';
  }
}

// ==============================================================================
// MODAL UNIFICADO DE CONFIRMACIÓN DESTRUCTIVA (UI02)
// ==============================================================================

function solicitarConfirmacionDestructiva({ titulo, mensaje, itemInfo, ejecutar }) {
  AppState.accionConfirmacion = ejecutar;

  const elTitulo = document.getElementById('confirm-modal-titulo');
  const elMensaje = document.getElementById('confirm-modal-mensaje');
  const elItemInfo = document.getElementById('confirm-modal-item-info');

  if (elTitulo) elTitulo.textContent = titulo || 'CONFIRMAR ACCIÓN';
  if (elMensaje) elMensaje.textContent = mensaje || '¿Estás seguro de que deseas proceder?';
  if (elItemInfo) elItemInfo.innerHTML = itemInfo || '';

  abrirModal('modal-confirmar-accion');
}

async function ejecutarConfirmacionDestructiva() {
  if (typeof AppState.accionConfirmacion !== 'function') {
    cerrarModal('modal-confirmar-accion');
    return;
  }

  const btnConfirmar = document.getElementById('btn-ejecutar-confirmacion');
  btnConfirmar.disabled = true;
  btnConfirmar.innerHTML = '<span class="spinner"></span> Procesando...';

  try {
    await AppState.accionConfirmacion();
  } finally {
    btnConfirmar.disabled = false;
    btnConfirmar.innerHTML = 'CONFIRMAR &rarr;';
    cerrarModal('modal-confirmar-accion');
    AppState.accionConfirmacion = null;
  }
}

// ==============================================================================
// UTILIDADES GENERALES
// ==============================================================================

function abrirModal(id) {
  const m = document.getElementById(id);
  if (m) {
    m.classList.add('open');
    // Enfocar primer campo interactivo
    const primerInput = m.querySelector('input:not([disabled]), select:not([disabled]), button:not([disabled])');
    if (primerInput) primerInput.focus();
  }
}

function cerrarModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('open');
}

function lanzarToast(tipo, titulo, mensaje) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `editorial-toast ${tipo}`;
  toast.setAttribute('role', 'alert');
  toast.innerHTML = `
    <div class="toast-head">${escaparHTML(titulo)}</div>
    <div class="toast-body">${escaparHTML(mensaje)}</div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.25s ease';
    setTimeout(() => toast.remove(), 260);
  }, 4200);
}

function formatearMoneda(val, moneda = 'COP') {
  const n = parseFloat(val) || 0;
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: moneda || 'COP',
    minimumFractionDigits: 2
  }).format(n);
}

function formatearNumero(valor) {
  const numero = Number(valor);
  return Number.isFinite(numero)
    ? new Intl.NumberFormat('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(numero)
    : '0,00';
}

function formatearMontosPorMoneda(montos) {
  const entradas = Object.entries(montos || {}).sort(([monedaA], [monedaB]) =>
    monedaA.localeCompare(monedaB)
  );
  return entradas.length
    ? entradas.map(([moneda, monto]) => `${moneda}: ${formatearMoneda(monto, moneda)}`).join(' · ')
    : formatearMoneda(0, 'COP');
}

function escaparHTML(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function copiarTexto(txt, aviso) {
  navigator.clipboard.writeText(txt).then(() => {
    lanzarToast('info', 'PORTAPAPELES', aviso);
  }).catch(() => {
    lanzarToast('error', 'ERROR', 'No se pudo copiar al portapapeles.');
  });
}

function colorearSintaxisJSON(json) {
  if (typeof json !== 'string') json = JSON.stringify(json, null, 2);
  json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return json.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    function (match) {
      let cls = 'json-number';
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? 'json-key' : 'json-string';
      } else if (/true|false/.test(match)) cls = 'json-boolean';
      else if (/null/.test(match)) cls = 'json-null';
      return `<span class="${cls}">${match}</span>`;
    }
  );
}

function configurarTema() {
  const toggle = document.getElementById('theme-toggle');
  toggle?.addEventListener('click', () => {
    const theme = document.documentElement.dataset.theme === THEME_DARK ? 'light' : THEME_DARK;
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    actualizarControlTema(theme);
  });

  actualizarControlTema(document.documentElement.dataset.theme);
}

function actualizarControlTema(theme) {
  const isDark = theme === THEME_DARK;
  const toggle = document.getElementById('theme-toggle');
  const icon = document.getElementById('theme-toggle-icon');
  const label = document.getElementById('theme-toggle-label');

  if (toggle) {
    toggle.setAttribute('aria-label', `Activar modo ${isDark ? 'claro' : 'oscuro'}`);
    toggle.setAttribute('aria-pressed', String(isDark));
  }
  if (icon) icon.textContent = isDark ? '☀' : '☾';
  if (label) label.textContent = isDark ? 'MODO CLARO' : 'MODO OSCURO';
}