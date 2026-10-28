/**
 * Pasarela / Studio - Frontend Minimalista
 * Manejo de estado, autenticación JWT, registro de usuarios,
 * control de roles (RBAC) y facturación en formato JSON.
 */

const AppState = {
  token: localStorage.getItem('pasarela_jwt_token') || null,
  usuarioActual: null,
  pagos: [],
  facturas: [],
  usuarios: [],
  pagoSeleccionadoParaFacturar: null,
  pagoEnEdicionId: null,
};

const THEME_STORAGE_KEY = 'pasarela_theme';
const THEME_DARK = 'dark';

document.documentElement.dataset.theme =
  localStorage.getItem(THEME_STORAGE_KEY) === THEME_DARK ? THEME_DARK : 'light';

document.addEventListener('DOMContentLoaded', async () => {
  configurarEventos();
  configurarTema();

  if (AppState.token) {
    await verificarSesionActual();
    actualizarEstadoVisualSesion(true);
  } else {
    actualizarEstadoVisualSesion(false);
  }

  await recargarTodo();
});

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

function configurarEventos() {
  // Pestañas de Navegación Principal
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.getAttribute('data-tab');
      cambiarPestana(tabId, btn);
    });
  });

  // Alternador entre Login y Registro
  const btnSwitchLogin = document.getElementById('btn-switch-login');
  const btnSwitchRegistro = document.getElementById('btn-switch-registro');
  const formLogin = document.getElementById('form-login');
  const formRegistro = document.getElementById('form-registro-normal');

  btnSwitchLogin?.addEventListener('click', () => {
    btnSwitchLogin.classList.add('active');
    btnSwitchRegistro.classList.remove('active');
    formLogin.classList.add('active');
    formRegistro.classList.remove('active');
  });

  btnSwitchRegistro?.addEventListener('click', () => {
    btnSwitchRegistro.classList.add('active');
    btnSwitchLogin.classList.remove('active');
    formRegistro.classList.add('active');
    formLogin.classList.remove('active');
  });

  // Relleno rápido en el formulario de Login
  document.getElementById('quick-fill-admin')?.addEventListener('click', () => {
    document.getElementById('login-username').value = 'admin';
    document.getElementById('login-password').value = 'admin123';
  });

  document.getElementById('quick-fill-user')?.addEventListener('click', () => {
    document.getElementById('login-username').value = 'usuario';
    document.getElementById('login-password').value = 'usuario123';
  });

  // Envíos de Formulario de Auth
  formLogin?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const u = document.getElementById('login-username').value.trim();
    const p = document.getElementById('login-password').value;
    await iniciarSesion(u, p, true);
  });

  formRegistro?.addEventListener('submit', guardarNuevoUsuarioNormal);

  // Cerrar sesión
  document.getElementById('btn-logout-header')?.addEventListener('click', cerrarSesion);

  // Botones de la tarjeta de sesión activa (cuando ya está logueado)
  document.getElementById('btn-session-goto-pagos')?.addEventListener('click', () => {
    cambiarPestana('tab-pagos', document.getElementById('tab-btn-pagos'));
  });

  document.getElementById('btn-session-goto-facturas')?.addEventListener('click', () => {
    cambiarPestana('tab-facturas', document.getElementById('tab-btn-facturas'));
  });

  document.getElementById('btn-session-create-user')?.addEventListener('click', () => {
    const unloggedBox = document.getElementById('auth-unlogged-box');
    const loggedBox = document.getElementById('auth-logged-box');
    if (loggedBox) loggedBox.classList.add('hidden');
    if (unloggedBox) unloggedBox.classList.remove('hidden');
    document.getElementById('btn-switch-registro')?.click();
  });

  document.getElementById('btn-session-logout')?.addEventListener('click', cerrarSesion);

  // Botones de cambio de rol en la sección 04
  document.getElementById('btn-switch-to-admin')?.addEventListener('click', () => {
    iniciarSesion('admin', 'admin123', true);
  });

  document.getElementById('btn-switch-to-user')?.addEventListener('click', () => {
    iniciarSesion('usuario', 'usuario123', true);
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

  // Modal Nuevo Pago
  document.getElementById('btn-abrir-modal-pago')?.addEventListener('click', () => {
    AppState.pagoEnEdicionId = null;
    document.getElementById('form-nuevo-pago').reset();
    document.getElementById('titulo-modal-pago').textContent = 'NUEVO PAGO SIMULADO';
    document.getElementById('btn-submit-pago').textContent = 'REGISTRAR PAGO →';
    abrirModal('modal-pago');
  });
  document.getElementById('form-nuevo-pago')?.addEventListener('submit', guardarPago);

  // Modal Facturación
  document.getElementById('btn-abrir-modal-factura')?.addEventListener('click', abrirModalFactura);
  document.getElementById('form-nueva-factura')?.addEventListener('submit', guardarNuevaFactura);

  document.querySelectorAll('input[name="modo-factura"]').forEach(radio => {
    radio.addEventListener('change', alternarModoFactura);
  });

  document.getElementById('factura-pago-id')?.addEventListener('change', alSeleccionarPagoEnFactura);
  document.getElementById('factura-iva-porcentaje')?.addEventListener('input', recalcularTotalesFactura);
  document.getElementById('btn-agregar-item')?.addEventListener('click', () => agregarFilaItemFactura());

  // Filtros de Pagos
  document.getElementById('filtro-pagos-cliente')?.addEventListener('input', filtrarPagos);
  document.getElementById('filtro-pagos-estado')?.addEventListener('change', filtrarPagos);

  document.getElementById('btn-actualizar-reportes')?.addEventListener('click', cargarReporteResumen);
  document.getElementById('form-divisas-convertir')?.addEventListener('submit', convertirMontoDivisas);

  // Consola Live
  document.querySelectorAll('.btn-console').forEach(btn => {
    btn.addEventListener('click', () => ejecutarAccionConsola(btn.getAttribute('data-action')));
  });

  document.getElementById('btn-copiar-consola')?.addEventListener('click', () => {
    copiarTexto(document.getElementById('console-output').innerText, 'JSON copiado al portapapeles');
  });

  document.getElementById('btn-copiar-visor')?.addEventListener('click', () => {
    copiarTexto(document.getElementById('visor-json-content').innerText, 'Factura JSON copiada');
  });

  document.getElementById('btn-descargar-json')?.addEventListener('click', descargarFacturaJSON);
}

// ==============================================================================
// AUTENTICACIÓN & SESIÓN
// ==============================================================================

async function iniciarSesion(username, password, mostrarToast = true) {
  try {
    const res = await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error de credenciales');

    AppState.token = data.token;
    AppState.usuarioActual = data.usuario;
    localStorage.setItem('pasarela_jwt_token', data.token);

    actualizarUIUsuario();
    actualizarEstadoVisualSesion(true);

    if (mostrarToast) {
      lanzarToast('success', 'SESIÓN INICIADA', `Autenticado como: ${username.toUpperCase()} (ROL: ${data.usuario.rol.toUpperCase()})`);
      // Redirigir automáticamente a la pestaña de Pagos para ver el dashboard
      cambiarPestana('tab-pagos', document.getElementById('tab-btn-pagos'));
    }

    await recargarTodo();
  } catch (err) {
    lanzarToast('error', 'ERROR DE LOGIN', err.message);
  }
}

async function verificarSesionActual() {
  try {
    const res = await fetch('/auth/me', {
      headers: { 'Authorization': `Bearer ${AppState.token}` }
    });

    if (res.ok) {
      const data = await res.json();
      AppState.usuarioActual = { username: data.username, rol: data.rol };
      actualizarUIUsuario();
      actualizarEstadoVisualSesion(true);
    } else {
      cerrarSesion(false);
    }
  } catch (err) {
    cerrarSesion(false);
  }
}

function cerrarSesion(mostrarToast = true) {
  AppState.token = null;
  AppState.usuarioActual = null;
  localStorage.removeItem('pasarela_jwt_token');

  actualizarEstadoVisualSesion(false);
  cambiarPestana('tab-auth', document.getElementById('tab-btn-auth'));

  document.getElementById('top-user-name').innerText = 'NO AUTENTICADO';
  document.getElementById('top-user-role').innerText = 'ANON';
  document.getElementById('session-user-name').innerText = 'SIN SESIÓN';
  document.getElementById('session-user-role').innerText = 'ROL: NINGUNO';
  document.getElementById('session-token-text').innerText = 'No hay token activo';
  renderizarTablaPagos(AppState.pagos);

  if (mostrarToast) {
    lanzarToast('info', 'SESIÓN FINALIZADA', 'Inicia sesión con un usuario para realizar transacciones.');
  }
}

function actualizarEstadoVisualSesion(estaLogueado) {
  const unloggedBox = document.getElementById('auth-unlogged-box');
  const loggedBox = document.getElementById('auth-logged-box');

  if (estaLogueado && AppState.usuarioActual) {
    if (unloggedBox) unloggedBox.classList.add('hidden');
    if (loggedBox) {
      loggedBox.classList.remove('hidden');
      document.getElementById('active-box-username').innerText = AppState.usuarioActual.username.toUpperCase();
      document.getElementById('active-box-role').innerText = `ROL: ${AppState.usuarioActual.rol.toUpperCase()}`;
    }
  } else {
    if (unloggedBox) unloggedBox.classList.remove('hidden');
    if (loggedBox) loggedBox.classList.add('hidden');
    const uInput = document.getElementById('login-username');
    const pInput = document.getElementById('login-password');
    if (uInput) uInput.value = '';
    if (pInput) pInput.value = '';
  }
  actualizarAccesoAPIs(Boolean(estaLogueado && AppState.token));
}

function actualizarAccesoAPIs(autenticado) {
  document.getElementById('reportes-sesion-requerida')?.classList.toggle('hidden', autenticado);
  document.getElementById('reportes-contenido')?.classList.toggle('hidden', !autenticado);
  document.getElementById('divisas-sesion-requerida')?.classList.toggle('hidden', autenticado);
  document.getElementById('divisas-contenido')?.classList.toggle('hidden', !autenticado);
}


function actualizarUIUsuario() {
  if (!AppState.usuarioActual) return;

  const { username, rol } = AppState.usuarioActual;
  const rolUpper = rol.toUpperCase();

  // Header
  document.getElementById('top-user-name').innerText = username;
  document.getElementById('top-user-role').innerText = rolUpper;

  // Panel de información de sesión
  document.getElementById('session-user-name').innerText = username;
  document.getElementById('session-user-role').innerText = `ROL: ${rolUpper}`;
  if (AppState.token) {
    document.getElementById('session-token-text').innerText = AppState.token;
  }

  // Métrica en pagos
  const metricRol = document.getElementById('metric-rol-status');
  const metricDesc = document.getElementById('metric-permisos-desc');
  if (metricRol) metricRol.innerText = rolUpper;
  if (metricDesc) {
    metricDesc.innerText = rol === 'admin' 
      ? 'Acceso total de escritura, modificación y borrado' 
      : 'Acceso estándar sin permisos destructivos';
  }
}

// ==============================================================================
// REGISTRO DE USUARIO NORMAL
// ==============================================================================

async function guardarNuevoUsuarioNormal(e) {
  e.preventDefault();
  const username = document.getElementById('registro-username').value.trim();
  const password = document.getElementById('registro-password').value;
  const email = document.getElementById('registro-email').value.trim() || null;

  try {
    const res = await fetch('/registro', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username,
        password,
        email,
        rol: 'usuario' // Se fuerza siempre como rol regular
      })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error al registrar usuario');

    lanzarToast('success', 'USUARIO REGISTRADO', `Cuenta '${username}' creada con rol USUARIO. Iniciando sesión...`);
    document.getElementById('form-registro-normal').reset();

    // Iniciar sesión automáticamente con el nuevo usuario
    await iniciarSesion(username, password, true);
  } catch (err) {
    lanzarToast('error', 'ERROR DE REGISTRO', err.message);
  }
}

// ==============================================================================
// RECARGA DE DATOS (PAGOS, FACTURAS, USUARIOS)
// ==============================================================================

async function recargarTodo() {
  await Promise.all([cargarPagos(), cargarFacturas(), cargarUsuarios()]);
}

async function cargarPagos() {
  try {
    const res = await fetch('/pagos');
    const data = await res.json();
    if (res.ok) {
      AppState.pagos = data;
      renderizarTablaPagos(data);
      actualizarMetricasPagos(data);
      actualizarSelectorPagosEnFacturas(data);
    }
  } catch (err) {
    console.error('Error cargando pagos:', err);
  }
}

function renderizarTablaPagos(pagos) {
  const tbody = document.getElementById('tbody-pagos');
  const countBadge = document.getElementById('count-pagos');
  const esAdmin = AppState.usuarioActual?.rol === 'admin';
  countBadge.innerText = pagos.length;

  if (pagos.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8">NO HAY PAGOS REGISTRADOS EN LA PASARELA.</td></tr>`;
    return;
  }

  tbody.innerHTML = pagos.map(p => `
    <tr>
      <td><strong>#${p.id}</strong></td>
      <td><strong>${escaparHTML(p.cliente)}</strong></td>
      <td><strong>${formatearMoneda(p.monto, p.moneda)}</strong></td>
      <td><span class="mono">${escaparHTML(p.metodo_pago.toUpperCase())}</span></td>
      <td><span class="status-pill ${p.estado}">${escaparHTML(p.estado.toUpperCase())}</span></td>
      <td><span class="mono">${escaparHTML(p.creado_por || 'admin')}</span></td>
      <td><span class="mono text-xs">${escaparHTML(p.fecha_creacion || '')}</span></td>
      <td class="text-right">
        <div class="table-actions">
          <button type="button" class="btn-table-action" onclick="iniciarFacturacionDePago(${p.id})">
            + FACTURAR
          </button>
          ${esAdmin ? `
            <button type="button" class="btn-table-action" onclick="iniciarEdicionPago(${p.id})">
              EDITAR
            </button>
            <button type="button" class="btn-table-action delete" onclick="eliminarPagoAccion(${p.id})">
              ELIMINAR
            </button>
          ` : ''}
        </div>
      </td>
    </tr>
  `).join('');
}

function actualizarMetricasPagos(pagos) {
  let total = 0;
  let aprobados = 0;
  let pendientes = 0;

  pagos.forEach(p => {
    total += parseFloat(p.monto) || 0;
    if (p.estado === 'aprobado') aprobados++;
    if (p.estado === 'pendiente') pendientes++;
  });

  document.getElementById('metric-total-monto').innerText = formatearMoneda(total, 'USD');
  document.getElementById('metric-total-pagos-count').innerText = `${pagos.length} transacciones registradas`;
  document.getElementById('metric-pagos-aprobados').innerText = aprobados;
  document.getElementById('metric-pagos-pendientes').innerText = pendientes;
}

function filtrarPagos() {
  const query = document.getElementById('filtro-pagos-cliente').value.toLowerCase();
  const estado = document.getElementById('filtro-pagos-estado').value;

  const filtrados = AppState.pagos.filter(p => {
    const matchC = !query || p.cliente.toLowerCase().includes(query);
    const matchE = !estado || p.estado === estado;
    return matchC && matchE;
  });

  renderizarTablaPagos(filtrados);
}

// ==============================================================================
// GESTIÓN DE FACTURAS EN FORMATO JSON
// ==============================================================================

async function cargarFacturas() {
  if (!AppState.token) return;

  try {
    const res = await fetch('/facturas', {
      headers: { 'Authorization': `Bearer ${AppState.token}` }
    });

    if (res.ok) {
      const data = await res.json();
      AppState.facturas = data;
      renderizarTablaFacturas(data);
      actualizarMetricasFacturas(data);
    }
  } catch (err) {
    console.error('Error cargando facturas:', err);
  }
}

function renderizarTablaFacturas(facturas) {
  const tbody = document.getElementById('tbody-facturas');
  const countBadge = document.getElementById('count-facturas');
  countBadge.innerText = facturas.length;

  if (facturas.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center py-8">NO SE HAN EMITIDO FACTURAS JSON TODAVÍA.</td></tr>`;
    return;
  }

  tbody.innerHTML = facturas.map(f => `
    <tr>
      <td><strong>${escaparHTML(f.numero_factura)}</strong></td>
      <td>
        <strong>${escaparHTML(f.cliente)}</strong>
        <div class="mono text-xs">${escaparHTML(f.email_cliente || '')}</div>
      </td>
      <td><span class="mono">${escaparHTML(f.documento_cliente || 'N/A')}</span></td>
      <td>
        ${f.pago_id ? `<span class="mono">PAGO #${f.pago_id}</span>` : `<span class="mono text-muted">DIRECTA</span>`}
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
          <button type="button" class="btn-table-action delete" onclick="eliminarFacturaAccion(${f.id})">
            ELIMINAR
          </button>
        </div>
      </td>
    </tr>
  `).join('');
}

function actualizarMetricasFacturas(facturas) {
  let total = 0;
  let totalIVA = 0;
  let pagadas = 0;
  let emitidas = 0;

  facturas.forEach(f => {
    total += parseFloat(f.total) || 0;
    totalIVA += parseFloat(f.impuesto) || 0;
    if (f.estado === 'pagada') pagadas++;
    if (f.estado === 'emitida') emitidas++;
  });

  document.getElementById('metric-facturado-total').innerText = formatearMoneda(total, 'COP');
  document.getElementById('metric-facturas-count').innerText = `${facturas.length} emitidas`;
  document.getElementById('metric-facturado-iva').innerText = formatearMoneda(totalIVA, 'COP');
  document.getElementById('metric-facturas-pagadas').innerText = pagadas;
  document.getElementById('metric-facturas-emitidas').innerText = emitidas;
}

// ==============================================================================
// MODAL DE FACTURACIÓN DINÁMICA
// ==============================================================================

function abrirModalFactura() {
  document.getElementById('form-nueva-factura').reset();
  document.getElementById('radio-factura-pago').checked = true;
  alternarModoFactura();

  if (AppState.pagoSeleccionadoParaFacturar) {
    document.getElementById('factura-pago-id').value = AppState.pagoSeleccionadoParaFacturar;
    alSeleccionarPagoEnFactura();
    AppState.pagoSeleccionadoParaFacturar = null;
  }

  abrirModal('modal-factura');
}

function alternarModoFactura() {
  const modo = document.querySelector('input[name="modo-factura"]:checked').value;
  const grupoPago = document.getElementById('grupo-selector-pago');
  const seccionItems = document.getElementById('seccion-items-factura');
  const esFacturaManual = modo === 'manual';
  const campoCliente = document.getElementById('factura-cliente');
  const camposItems = document.querySelectorAll('#items-container input');

  campoCliente.required = esFacturaManual;
  camposItems.forEach(campo => {
    campo.disabled = !esFacturaManual;
  });

  if (!esFacturaManual) {
    grupoPago.classList.remove('hidden');
    seccionItems.classList.add('hidden');
    alSeleccionarPagoEnFactura();
  } else {
    grupoPago.classList.add('hidden');
    seccionItems.classList.remove('hidden');

    const container = document.getElementById('items-container');
    if (container.children.length === 0) {
      agregarFilaItemFactura();
    }
    recalcularTotalesFactura();
  }
}

function actualizarSelectorPagosEnFacturas(pagos) {
  const select = document.getElementById('factura-pago-id');
  select.innerHTML = '<option value="">Selecciona un pago registrado...</option>' +
    pagos.map(p => `
      <option value="${p.id}" data-cliente="${escaparHTML(p.cliente)}" data-monto="${p.monto}" data-moneda="${p.moneda}">
        Pago #${p.id} - ${escaparHTML(p.cliente)} (${formatearMoneda(p.monto, p.moneda)}) [${p.estado.toUpperCase()}]
      </option>
    `).join('');
}

function alSeleccionarPagoEnFactura() {
  const select = document.getElementById('factura-pago-id');
  const opt = select.options[select.selectedIndex];
  if (!opt || !opt.value) {
    document.getElementById('factura-cliente').value = '';
    document.getElementById('prev-subtotal').innerText = '$0.00';
    document.getElementById('prev-iva').innerText = '$0.00';
    document.getElementById('prev-total').innerText = '$0.00';
    return;
  }

  const cliente = opt.getAttribute('data-cliente');
  const monto = parseFloat(opt.getAttribute('data-monto')) || 0;
  const moneda = opt.getAttribute('data-moneda') || 'COP';

  document.getElementById('factura-cliente').value = cliente;
  document.getElementById('factura-moneda').value = moneda;

  const tasa = parseFloat(document.getElementById('factura-iva-porcentaje').value) || 0;
  const iva = monto * (tasa / 100);
  const total = monto + iva;

  document.getElementById('prev-subtotal').innerText = formatearMoneda(monto, moneda);
  document.getElementById('prev-iva-tasa').innerText = tasa.toFixed(1);
  document.getElementById('prev-iva').innerText = formatearMoneda(iva, moneda);
  document.getElementById('prev-total').innerText = formatearMoneda(total, moneda);
}

function agregarFilaItemFactura(desc = '', cant = 1, precio = 0) {
  const container = document.getElementById('items-container');
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

  row.querySelector('.btn-remove-row').addEventListener('click', () => {
    if (container.children.length > 1) {
      row.remove();
      recalcularTotalesFactura();
    } else {
      lanzarToast('info', 'REQUERIMIENTO', 'La factura debe tener al menos un ítem.');
    }
  });

  container.appendChild(row);
  recalcularTotalesFactura();
}

function recalcularTotalesFactura() {
  const modo = document.querySelector('input[name="modo-factura"]:checked').value;
  if (modo === 'pago') {
    alSeleccionarPagoEnFactura();
    return;
  }

  const container = document.getElementById('items-container');
  let subtotal = 0;

  Array.from(container.children).forEach(row => {
    const cant = parseFloat(row.querySelector('.item-cant').value) || 0;
    const precio = parseFloat(row.querySelector('.item-precio').value) || 0;
    subtotal += (cant * precio);
  });

  const moneda = document.getElementById('factura-moneda').value;
  const tasa = parseFloat(document.getElementById('factura-iva-porcentaje').value) || 0;
  const iva = subtotal * (tasa / 100);
  const total = subtotal + iva;

  document.getElementById('prev-subtotal').innerText = formatearMoneda(subtotal, moneda);
  document.getElementById('prev-iva-tasa').innerText = tasa.toFixed(1);
  document.getElementById('prev-iva').innerText = formatearMoneda(iva, moneda);
  document.getElementById('prev-total').innerText = formatearMoneda(total, moneda);
}

function iniciarFacturacionDePago(pagoId) {
  AppState.pagoSeleccionadoParaFacturar = pagoId;
  cambiarPestana('tab-facturas', document.getElementById('tab-btn-facturas'));
  abrirModalFactura();
}

// ==============================================================================
// ENVÍO DE ACCIONES A LA API (MUTACIONES)
// ==============================================================================

function iniciarEdicionPago(pagoId) {
  if (AppState.usuarioActual?.rol !== 'admin') {
    lanzarToast('forbidden', '403 FORBIDDEN', 'Solo un administrador puede modificar pagos.');
    return;
  }

  const pago = AppState.pagos.find(item => item.id === pagoId);
  if (!pago) {
    lanzarToast('error', 'PAGO NO DISPONIBLE', 'No se encontró el pago para editar. Actualiza la lista e inténtalo de nuevo.');
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
  if (!AppState.token) {
    lanzarToast('forbidden', 'NO AUTENTICADO', 'Inicia sesión primero para registrar un pago.');
    return;
  }
  if (AppState.pagoEnEdicionId && AppState.usuarioActual?.rol !== 'admin') {
    lanzarToast('forbidden', '403 FORBIDDEN', 'Solo un administrador puede modificar pagos.');
    return;
  }

  const payload = {
    cliente: document.getElementById('pago-cliente').value.trim(),
    monto: parseFloat(document.getElementById('pago-monto').value),
    moneda: document.getElementById('pago-moneda').value,
    metodo_pago: document.getElementById('pago-metodo').value,
    estado: document.getElementById('pago-estado').value,
  };
  const pagoId = AppState.pagoEnEdicionId;

  try {
    const res = await fetch(pagoId ? `/pagos/${pagoId}` : '/pagos', {
      method: pagoId ? 'PUT' : 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AppState.token}`
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (res.status === 403) {
      lanzarToast('forbidden', '403 FORBIDDEN', 'Solo un administrador puede modificar pagos.');
      return;
    }
    if (!res.ok) throw new Error(data.error || 'Error registrando pago');

    cerrarModal('modal-pago');
    AppState.pagoEnEdicionId = null;
    document.getElementById('form-nuevo-pago').reset();
    document.getElementById('titulo-modal-pago').textContent = 'NUEVO PAGO SIMULADO';
    document.getElementById('btn-submit-pago').textContent = 'REGISTRAR PAGO →';
    lanzarToast(
      'success',
      pagoId ? 'PAGO ACTUALIZADO' : 'PAGO REGISTRADO',
      pagoId ? `Pago #${data.id} actualizado correctamente.` : `Pago #${data.id} creado con éxito para ${data.cliente}`
    );
    await recargarTodo();
  } catch (err) {
    lanzarToast('error', 'ERROR', err.message);
  }
}

async function guardarNuevaFactura(e) {
  e.preventDefault();
  if (!AppState.token) {
    lanzarToast('forbidden', 'NO AUTENTICADO', 'Inicia sesión primero para emitir facturas.');
    return;
  }

  const modo = document.querySelector('input[name="modo-factura"]:checked').value;
  let payload = {
    cliente: document.getElementById('factura-cliente').value.trim(),
    email_cliente: document.getElementById('factura-email').value.trim() || null,
    documento_cliente: document.getElementById('factura-documento').value.trim() || null,
    moneda: document.getElementById('factura-moneda').value,
    porcentaje_impuesto: parseFloat(document.getElementById('factura-iva-porcentaje').value) || 0,
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
    Array.from(document.getElementById('items-container').children).forEach(row => {
      const desc = row.querySelector('.item-desc').value.trim();
      const cant = Number.parseFloat(row.querySelector('.item-cant').value);
      const precio = Number.parseFloat(row.querySelector('.item-precio').value);
      if (desc && Number.isFinite(cant) && Number.isFinite(precio)) {
        items.push({ descripcion: desc, cantidad: cant, precio_unitario: precio });
      }
    });

    if (items.length === 0) {
      lanzarToast('error', 'SIN ARTÍCULOS', 'Agrega al menos una línea a la factura.');
      return;
    }
    payload.items = items;
  }

  try {
    const res = await fetch('/facturas', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AppState.token}`
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error emitiendo factura');

    cerrarModal('modal-factura');
    lanzarToast('success', 'FACTURA EMITIDA', `Factura #${data.numero_factura} generada en formato JSON.`);
    await recargarTodo();
    verFacturaFormatoEstandar(data.id);
  } catch (err) {
    lanzarToast('error', 'ERROR FACTURA', err.message);
  }
}

async function eliminarPagoAccion(pagoId) {
  if (!AppState.token) {
    lanzarToast('forbidden', 'NO AUTENTICADO', 'Inicia sesión primero.');
    return;
  }

  try {
    const res = await fetch(`/pagos/${pagoId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${AppState.token}` }
    });

    const data = await res.json();
    if (res.status === 403) {
      lanzarToast('forbidden', '403 FORBIDDEN', '¡Permiso denegado! Tu rol no tiene autorización para eliminar pagos. Se requiere rol ADMIN.');
      return;
    }

    if (!res.ok) throw new Error(data.error || 'No se pudo eliminar el pago');

    lanzarToast('success', 'PAGO ELIMINADO', `Pago #${pagoId} borrado correctamente.`);
    await recargarTodo();
  } catch (err) {
    lanzarToast('error', 'ERROR', err.message);
  }
}

async function eliminarFacturaAccion(facturaId) {
  if (!AppState.token) {
    lanzarToast('forbidden', 'NO AUTENTICADO', 'Inicia sesión primero.');
    return;
  }

  try {
    const res = await fetch(`/facturas/${facturaId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${AppState.token}` }
    });

    const data = await res.json();
    if (res.status === 403) {
      lanzarToast('forbidden', '403 FORBIDDEN', 'Solo un administrador puede eliminar facturas del sistema.');
      return;
    }

    if (!res.ok) throw new Error(data.error || 'No se pudo eliminar la factura');

    lanzarToast('success', 'FACTURA ELIMINADA', `Factura #${facturaId} eliminada.`);
    await recargarTodo();
  } catch (err) {
    lanzarToast('error', 'ERROR', err.message);
  }
}

// ==============================================================================
// VISOR DE FACTURACIÓN ELECTRÓNICA JSON
// ==============================================================================

async function verFacturaFormatoEstandar(facturaId) {
  try {
    const res = await fetch(`/facturas/${facturaId}/json`, {
      headers: { 'Authorization': `Bearer ${AppState.token}` }
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'No se pudo cargar la factura');

    document.getElementById('visor-numero-factura').innerText = `FACTURA #${data.encabezado.numero_factura}`;
    document.getElementById('visor-tipo-doc').innerText = `${data.encabezado.tipo_documento.toUpperCase()} // SHA-256 VERIFICADO`;

    const codeEl = document.getElementById('visor-json-content');
    codeEl.innerHTML = colorearSintaxisJSON(JSON.stringify(data, null, 2));

    abrirModal('modal-visor-json');
  } catch (err) {
    lanzarToast('error', 'ERROR VISOR', err.message);
  }
}

function descargarFacturaJSON() {
  const content = document.getElementById('visor-json-content').innerText;
  const blob = new Blob([content], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `factura_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
  lanzarToast('info', 'DESCARGA', 'Factura JSON descargada.');
}

// ==============================================================================
// USUARIOS Y RBAC
// ==============================================================================

async function cargarUsuarios() {
  const tbody = document.getElementById('tbody-usuarios');
  if (!AppState.token) return;

  try {
    const res = await fetch('/usuarios', {
      headers: { 'Authorization': `Bearer ${AppState.token}` }
    });

    if (res.status === 403) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="text-center py-8">
            <strong>[ 403 FORBIDDEN ]</strong> La consulta de usuarios registrados requiere rol de Administrador.
          </td>
        </tr>
      `;
      return;
    }

    if (res.ok) {
      const data = await res.json();
      AppState.usuarios = data;
      renderizarTablaUsuarios(data);
    }
  } catch (err) {
    console.error('Error cargando usuarios:', err);
  }
}

function renderizarTablaUsuarios(usuarios) {
  const tbody = document.getElementById('tbody-usuarios');
  if (usuarios.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center py-8">NO HAY USUARIOS REGISTRADOS.</td></tr>`;
    return;
  }

  tbody.innerHTML = usuarios.map(u => `
    <tr>
      <td><strong>#${u.id}</strong></td>
      <td><strong>${escaparHTML(u.username)}</strong></td>
      <td>
        <span class="status-pill ${u.rol === 'admin' ? 'aprobado' : 'pendiente'}">
          ${escaparHTML(u.rol.toUpperCase())}
        </span>
      </td>
      <td><span class="mono">${escaparHTML(u.email || 'N/A')}</span></td>
      <td><span class="mono text-xs">${escaparHTML(u.fecha_creacion || '')}</span></td>
    </tr>
  `).join('');
}

// ==============================================================================
// REPORTES Y CONVERSIÓN DE DIVISAS
// ==============================================================================

async function cargarReporteResumen() {
  const estado = document.getElementById('reportes-estado');
  if (!AppState.token) {
    estado.textContent = 'Inicia sesión para usar esta función.';
    return;
  }

  estado.className = 'api-status';
  estado.textContent = 'Cargando reportes...';
  try {
    const res = await fetch('/api/reportes/resumen', {
      headers: { 'Authorization': `Bearer ${AppState.token}` }
    });
    const data = await res.json();

    if (res.status === 401) {
      estado.className = 'api-status error';
      estado.textContent = 'Tu sesión venció o no es válida. Inicia sesión nuevamente para consultar los reportes.';
      return;
    }
    if (res.status === 503) {
      estado.className = 'api-status error';
      estado.textContent = 'El servicio de reportes no está disponible. Inicia reportes_api en el puerto 5001.';
      return;
    }
    if (!res.ok) throw new Error(data.error || 'No se pudieron cargar los reportes.');

    const pagos = data.pagos || {};
    const facturas = data.facturas || {};
    document.getElementById('reporte-total-transacciones').textContent =
      String(pagos.total_transacciones ?? 0);
    document.getElementById('reporte-monto-total').textContent =
      formatearNumero(pagos.monto_total);
    document.getElementById('reporte-total-facturas').textContent =
      String(facturas.total_facturas ?? 0);
    document.getElementById('reporte-total-iva').textContent =
      formatearNumero(facturas.total_iva_recaudado);
    renderizarTablaConteos(pagos.por_estado, 'reporte-por-estado');
    renderizarTablaConteos(pagos.por_metodo, 'reporte-por-metodo');
    renderizarTablaMonedas(pagos.por_moneda);
    renderizarTopClientes(facturas.top_clientes);
    estado.textContent = 'Reportes actualizados correctamente.';
  } catch (err) {
    estado.className = 'api-status error';
    estado.textContent = err.message || 'No se pudieron cargar los reportes.';
  }
}

function renderizarTablaConteos(datos, idTbody) {
  const tbody = document.getElementById(idTbody);
  const filas = Object.entries(datos || {});
  tbody.innerHTML = filas.length
    ? filas.map(([nombre, cantidad]) => `
      <tr><td>${escaparHTML(nombre)}</td><td class="text-right">${escaparHTML(String(cantidad ?? 0))}</td></tr>
    `).join('')
    : '<tr><td colspan="2">Sin datos</td></tr>';
}

function renderizarTablaMonedas(datos) {
  const tbody = document.getElementById('reporte-por-moneda');
  const filas = Object.entries(datos || {});
  tbody.innerHTML = filas.length
    ? filas.map(([moneda, detalle]) => `
      <tr>
        <td>${escaparHTML(moneda)}</td>
        <td class="text-right">${escaparHTML(String(detalle.cantidad ?? 0))}</td>
        <td class="text-right">${formatearNumero(detalle.monto)}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="3">Sin datos</td></tr>';
}

function renderizarTopClientes(clientes) {
  const tbody = document.getElementById('reporte-top-clientes');
  tbody.innerHTML = Array.isArray(clientes) && clientes.length
    ? clientes.map(cliente => `
      <tr>
        <td>${escaparHTML(cliente.cliente)}</td>
        <td class="text-right">${formatearNumero(cliente.total)}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="2">Sin datos</td></tr>';
}

function formatearNumero(valor) {
  const numero = Number(valor);
  return Number.isFinite(numero)
    ? new Intl.NumberFormat('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(numero)
    : '0,00';
}

async function convertirMontoDivisas(e) {
  e.preventDefault();
  const estado = document.getElementById('divisas-estado');
  if (!AppState.token) {
    estado.textContent = 'Inicia sesión para usar esta función.';
    return;
  }

  const parametros = new URLSearchParams({
    monto: document.getElementById('divisas-monto').value,
    de: document.getElementById('divisas-de').value,
    a: document.getElementById('divisas-a').value
  });
  estado.className = 'api-status';
  estado.textContent = 'Consultando tasa y convirtiendo...';
  try {
    const res = await fetch(`/divisas/convertir?${parametros.toString()}`, {
      headers: { 'Authorization': `Bearer ${AppState.token}` }
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'No se pudo convertir el monto.');

    const fuente = data.fuente === 'respaldo_local'
      ? 'Respaldo local (tasas aproximadas)'
      : 'API en vivo (open.er-api.com)';
    document.getElementById('divisas-resultado').textContent =
      `${formatearMoneda(data.resultado, data.a)} ${data.a}`;
    document.getElementById('divisas-tasa').textContent =
      `Tasa: 1 ${data.de} = ${formatearNumero(data.tasa)} ${data.a}`;
    document.getElementById('divisas-fuente').textContent = `Fuente: ${fuente}`;
    document.getElementById('divisas-fecha').textContent =
      `Actualización: ${data.fecha_actualizacion}`;
    estado.textContent = 'Conversión completada.';
  } catch (err) {
    estado.className = 'api-status error';
    estado.textContent = err.message || 'No se pudo convertir el monto.';
  }
}

// ==============================================================================
// CONSOLA API
// ==============================================================================

async function ejecutarAccionConsola(action) {
  const methodEl = document.getElementById('console-method');
  const urlEl = document.getElementById('console-url');
  const statusEl = document.getElementById('console-status');
  const outputEl = document.getElementById('console-output');

  let endpoint = '/auth/me';
  let method = 'GET';

  if (action === 'get-me') endpoint = '/auth/me';
  else if (action === 'get-pagos') endpoint = '/pagos';
  else if (action === 'get-facturas') endpoint = '/facturas';
  else if (action === 'get-usuarios') endpoint = '/usuarios';
  else if (action === 'get-reporte-resumen') endpoint = '/api/reportes/resumen';
  else if (action === 'get-divisas-convertir') {
    endpoint = '/divisas/convertir?monto=100&de=USD&a=COP';
  }
  else if (action === 'forzar-403') {
    endpoint = '/pagos/1';
    method = 'DELETE';
  }

  methodEl.innerText = method;
  urlEl.innerText = endpoint;
  outputEl.innerHTML = '// Ejecutando llamada HTTP...';

  try {
    const res = await fetch(endpoint, {
      method: method,
      headers: {
        ...(AppState.token ? { 'Authorization': `Bearer ${AppState.token}` } : {})
      }
    });

    statusEl.innerText = `${res.status} ${res.statusText || ''}`;
    const json = await res.json();
    outputEl.innerHTML = colorearSintaxisJSON(JSON.stringify(json, null, 2));

    if (res.status === 403) {
      lanzarToast('forbidden', '403 FORBIDDEN DETECTADO', 'Petición bloqueada por falta de privilegios.');
    }
  } catch (err) {
    outputEl.innerText = `Error: ${err.message}`;
  }
}

// ==============================================================================
// UTILIDADES
// ==============================================================================

function cambiarPestana(tabId, clickedBtn) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));

  const pane = document.getElementById(tabId);
  if (pane) pane.classList.add('active');
  if (clickedBtn) clickedBtn.classList.add('active');
}

function abrirModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('open');
}

function cerrarModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('open');
}

function lanzarToast(tipo, titulo, mensaje) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `editorial-toast ${tipo}`;
  toast.innerHTML = `
    <div class="toast-head">${escaparHTML(titulo)}</div>
    <div class="toast-body">${escaparHTML(mensaje)}</div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.2s ease';
    setTimeout(() => toast.remove(), 250);
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
    lanzarToast('error', 'ERROR', 'No se pudo copiar.');
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
