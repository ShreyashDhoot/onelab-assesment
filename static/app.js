/**
 * FinRecon Frontend Application Logic
 */

// Application State
const state = {
  reconciledData: null,
  allGroups: [],
  filteredGroups: [],
  currentPage: 1,
  pageSize: 25,
  filters: {
    gapType: 'ALL',
    status: 'ALL',
    method: 'ALL',
    anomalyType: 'ALL',
    search: ''
  },
  platformFile: null,
  bankFile: null
};

// DOM Elements
const dom = {
  platformFileInput: document.getElementById('platformFileInput'),
  bankFileInput: document.getElementById('bankFileInput'),
  platformFileLabel: document.getElementById('platformFileLabel'),
  bankFileLabel: document.getElementById('bankFileLabel'),
  platformDropZone: document.getElementById('platformDropZone'),
  bankDropZone: document.getElementById('bankDropZone'),
  btnLoadSample: document.getElementById('btnLoadSample'),
  btnReconcile: document.getElementById('btnReconcile'),
  btnBenchmark: document.getElementById('btnBenchmark'),
  btnExport: document.getElementById('btnExport'),
  statusMessage: document.getElementById('statusMessage'),

  // KPIs
  kpiPlatformEff: document.getElementById('kpiPlatformEff'),
  kpiPlatformGross: document.getElementById('kpiPlatformGross'),
  kpiPlatformCount: document.getElementById('kpiPlatformCount'),
  kpiBankEff: document.getElementById('kpiBankEff'),
  kpiBankGross: document.getElementById('kpiBankGross'),
  kpiBankCount: document.getElementById('kpiBankCount'),
  kpiFinalGap: document.getElementById('kpiFinalGap'),
  kpiGapStatus: document.getElementById('kpiGapStatus'),
  kpiCutoffGap: document.getElementById('kpiCutoffGap'),
  kpiTransitDelta: document.getElementById('kpiTransitDelta'),
  kpiCleanCount: document.getElementById('kpiCleanCount'),
  kpiCleanInr: document.getElementById('kpiCleanInr'),
  kpiAnomalyCount: document.getElementById('kpiAnomalyCount'),
  kpiTotalGroups: document.getElementById('kpiTotalGroups'),

  // Gap breakdown cards
  gapCountTiming: document.getElementById('gapCountTiming'),
  gapFinalTiming: document.getElementById('gapFinalTiming'),
  gapCutoffTiming: document.getElementById('gapCutoffTiming'),

  gapCountAmount: document.getElementById('gapCountAmount'),
  gapFinalAmount: document.getElementById('gapFinalAmount'),
  gapPlatAmount: document.getElementById('gapPlatAmount'),

  gapCountStatus: document.getElementById('gapCountStatus'),
  gapFinalStatus: document.getElementById('gapFinalStatus'),
  gapBankStatus: document.getElementById('gapBankStatus'),

  gapCountOperational: document.getElementById('gapCountOperational'),
  gapFinalOperational: document.getElementById('gapFinalOperational'),
  gapPlatOperational: document.getElementById('gapPlatOperational'),

  gapCountUnmatchedP: document.getElementById('gapCountUnmatchedP'),
  gapFinalUnmatchedP: document.getElementById('gapFinalUnmatchedP'),

  gapCountUnmatchedB: document.getElementById('gapCountUnmatchedB'),
  gapFinalUnmatchedB: document.getElementById('gapFinalUnmatchedB'),

  // Toolbar & Table
  searchInput: document.getElementById('searchInput'),
  gapTypeSelect: document.getElementById('gapTypeSelect'),
  statusFilterSelect: document.getElementById('statusFilterSelect'),
  methodSelect: document.getElementById('methodSelect'),
  btnResetFilters: document.getElementById('btnResetFilters'),
  filterChips: document.getElementById('filterChips'),
  tableBody: document.getElementById('tableBody'),
  tableRecordCount: document.getElementById('tableRecordCount'),
  btnPrevPage: document.getElementById('btnPrevPage'),
  btnNextPage: document.getElementById('btnNextPage'),
  pageInfo: document.getElementById('pageInfo'),

  // Modals
  detailModal: document.getElementById('detailModal'),
  modalGroupId: document.getElementById('modalGroupId'),
  modalTitle: document.getElementById('modalTitle'),
  modalBody: document.getElementById('modalBody'),

  benchmarkModal: document.getElementById('benchmarkModal'),
  benchmarkLoading: document.getElementById('benchmarkLoading'),
  benchmarkContent: document.getElementById('benchmarkContent')
};

// -------------------------------------------------------------
// Formatters
// -------------------------------------------------------------
function formatINR(val) {
  if (val === null || val === undefined) return '₹0.00';
  const num = Number(val);
  const sign = num < 0 ? '-' : '';
  const abs = Math.abs(num);
  return `${sign}₹${abs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function showStatus(text, type = 'info') {
  dom.statusMessage.className = `status-msg ${type}`;
  dom.statusMessage.textContent = text;
  dom.statusMessage.classList.remove('hidden');
}

function hideStatus() {
  dom.statusMessage.classList.add('hidden');
}

// -------------------------------------------------------------
// Event Listeners
// -------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  setupFileUploads();
  setupActionButtons();
  setupFilterHandlers();

  // Auto-load sample data on first visit for instant demo UX
  loadSampleData();
});

function setupFileUploads() {
  // Platform File
  dom.platformFileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
      state.platformFile = e.target.files[0];
      dom.platformFileLabel.textContent = state.platformFile.name;
    }
  });

  // Bank File
  dom.bankFileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
      state.bankFile = e.target.files[0];
      dom.bankFileLabel.textContent = state.bankFile.name;
    }
  });

  // Drag & drop support
  [dom.platformDropZone, dom.bankDropZone].forEach((zone) => {
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  });

  dom.platformDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dom.platformDropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
      state.platformFile = e.dataTransfer.files[0];
      dom.platformFileLabel.textContent = state.platformFile.name;
    }
  });

  dom.bankDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dom.bankDropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
      state.bankFile = e.dataTransfer.files[0];
      dom.bankFileLabel.textContent = state.bankFile.name;
    }
  });
}

function setupActionButtons() {
  dom.btnLoadSample.addEventListener('click', loadSampleData);
  dom.btnReconcile.addEventListener('click', reconcileUploadedFiles);
  dom.btnBenchmark.addEventListener('click', openBenchmarkModal);
  dom.btnExport.addEventListener('click', exportCSV);

  dom.btnPrevPage.addEventListener('click', () => {
    if (state.currentPage > 1) {
      state.currentPage--;
      renderTable();
    }
  });

  dom.btnNextPage.addEventListener('click', () => {
    const totalPages = Math.ceil(state.filteredGroups.length / state.pageSize);
    if (state.currentPage < totalPages) {
      state.currentPage++;
      renderTable();
    }
  });
}

function setupFilterHandlers() {
  dom.searchInput.addEventListener('input', (e) => {
    state.filters.search = e.target.value.toLowerCase().trim();
    state.currentPage = 1;
    applyFilters();
  });

  dom.gapTypeSelect.addEventListener('change', (e) => {
    state.filters.gapType = e.target.value;
    state.currentPage = 1;
    updateActiveGapCard(e.target.value);
    applyFilters();
  });

  dom.statusFilterSelect.addEventListener('change', (e) => {
    state.filters.status = e.target.value;
    state.currentPage = 1;
    applyFilters();
  });

  dom.methodSelect.addEventListener('change', (e) => {
    state.filters.method = e.target.value;
    state.currentPage = 1;
    applyFilters();
  });

  dom.btnResetFilters.addEventListener('click', () => {
    state.filters = {
      gapType: 'ALL',
      status: 'ALL',
      method: 'ALL',
      anomalyType: 'ALL',
      search: ''
    };
    dom.searchInput.value = '';
    dom.gapTypeSelect.value = 'ALL';
    dom.statusFilterSelect.value = 'ALL';
    dom.methodSelect.value = 'ALL';
    updateActiveGapCard('ALL');
    state.currentPage = 1;
    applyFilters();
  });
}

// -------------------------------------------------------------
// Core Actions: Reconcile, Sample, Benchmark
// -------------------------------------------------------------
async function loadSampleData() {
  try {
    showStatus('Loading pre-built transaction datasets and running reconciliation engine...', 'info');
    dom.btnLoadSample.disabled = true;

    const res = await fetch('/api/reconcile-sample', { method: 'POST' });
    const data = await res.json();

    if (!data.success) {
      throw new Error(data.error || 'Failed to load sample data.');
    }

    state.reconciledData = data.data;
    state.allGroups = data.data.groups;
    dom.btnExport.disabled = false;

    dom.platformFileLabel.textContent = 'platform_transactions.csv (Sample)';
    dom.bankFileLabel.textContent = 'bank_transactions.csv (Sample)';

    updateUI();
    showStatus('Reconciliation complete: 500 platform transactions vs 495 bank transactions analyzed.', 'info');
  } catch (err) {
    showStatus(`Error loading sample data: ${err.message}`, 'error');
  } finally {
    dom.btnLoadSample.disabled = false;
  }
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

async function reconcileUploadedFiles() {
  // If user hasn't selected custom files yet, reconcile sample data
  if (!state.platformFile || !state.bankFile) {
    showStatus('No custom files selected. Reconciling built-in sample transaction data...', 'info');
    return loadSampleData();
  }

  try {
    showStatus('Reading files and executing multi-pass reconciliation...', 'info');
    dom.btnReconcile.disabled = true;

    const pText = await readFileAsText(state.platformFile);
    const bText = await readFileAsText(state.bankFile);

    const res = await fetch('/api/reconcile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        platform_csv: pText,
        bank_csv: bText,
        platform_filename: state.platformFile.name,
        bank_filename: state.bankFile.name
      })
    });
    const data = await res.json();

    if (!data.success) {
      throw new Error(data.error || 'Reconciliation failed.');
    }

    state.reconciledData = data.data;
    state.allGroups = data.data.groups;
    dom.btnExport.disabled = false;

    updateUI();
    showStatus(`Reconciliation complete! Analyzed ${data.data.platform_rows_count} platform rows and ${data.data.bank_rows_count} bank rows.`, 'info');
  } catch (err) {
    showStatus(`Reconciliation Error: ${err.message}`, 'error');
  } finally {
    dom.btnReconcile.disabled = false;
  }
}

function exportCSV() {
  window.location.href = '/api/export';
}

// -------------------------------------------------------------
// UI Updates
// -------------------------------------------------------------
function updateUI() {
  if (!state.reconciledData) return;
  const kpis = state.reconciledData.kpis;

  // Executive KPI Cards
  dom.kpiPlatformEff.textContent = formatINR(kpis.platform_effective_inr);
  dom.kpiPlatformGross.textContent = `Gross: ${formatINR(kpis.platform_gross_inr)} (SUCCESS only)`;
  dom.kpiPlatformCount.textContent = `${kpis.platform_rows_total} rows`;

  dom.kpiBankEff.textContent = formatINR(kpis.bank_effective_inr);
  dom.kpiBankGross.textContent = `Gross: ${formatINR(kpis.bank_gross_inr)} (Credit - Debit)`;
  dom.kpiBankCount.textContent = `${kpis.bank_rows_total} rows`;

  dom.kpiFinalGap.textContent = formatINR(kpis.final_gap_inr);
  dom.kpiFinalGap.className = `kpi-value ${kpis.final_gap_inr === 0 ? 'text-green' : 'text-red'}`;
  dom.kpiGapStatus.textContent = kpis.final_gap_inr === 0 ? 'Balanced' : 'Residual Gap';
  dom.kpiGapStatus.className = `kpi-badge ${kpis.final_gap_inr === 0 ? 'kpi-badge-green' : 'kpi-badge-red'}`;

  dom.kpiCutoffGap.textContent = formatINR(kpis.cutoff_gap_inr);
  dom.kpiTransitDelta.textContent = `Transit in-flight: ${formatINR(kpis.timing_transit_gap_inr)}`;

  dom.kpiCleanCount.textContent = kpis.clean_matches_count;
  dom.kpiCleanInr.textContent = `Volume: ${formatINR(kpis.clean_matches_inr)}`;

  dom.kpiAnomalyCount.textContent = kpis.anomaly_groups_count;
  dom.kpiTotalGroups.textContent = `Total Groups: ${kpis.total_groups}`;

  // 4 Gap Types + Unmatched Cards
  const gapBD = kpis.gap_types_breakdown || {};

  const timing = gapBD.TIMING || { count: 0, gap_final_inr: 0, gap_cutoff_inr: 0 };
  dom.gapCountTiming.textContent = `${timing.count} Groups`;
  dom.gapFinalTiming.textContent = formatINR(timing.gap_final_inr);
  dom.gapCutoffTiming.textContent = formatINR(timing.gap_cutoff_inr);

  const amount = gapBD.AMOUNT || { count: 0, gap_final_inr: 0, platform_inr: 0 };
  dom.gapCountAmount.textContent = `${amount.count} Groups`;
  dom.gapFinalAmount.textContent = formatINR(amount.gap_final_inr);
  dom.gapPlatAmount.textContent = formatINR(amount.platform_inr);

  const status = gapBD.STATUS || { count: 0, gap_final_inr: 0, bank_inr: 0 };
  dom.gapCountStatus.textContent = `${status.count} Groups`;
  dom.gapFinalStatus.textContent = formatINR(status.gap_final_inr);
  dom.gapBankStatus.textContent = formatINR(status.bank_inr);

  const oper = gapBD.OPERATIONAL || { count: 0, gap_final_inr: 0, platform_inr: 0 };
  dom.gapCountOperational.textContent = `${oper.count} Groups`;
  dom.gapFinalOperational.textContent = formatINR(oper.gap_final_inr);
  dom.gapPlatOperational.textContent = `${oper.count}`;

  const unmatP = gapBD.UNMATCHED_PLATFORM || { count: 0, gap_final_inr: 0 };
  dom.gapCountUnmatchedP.textContent = `${unmatP.count} Rows`;
  dom.gapFinalUnmatchedP.textContent = formatINR(unmatP.gap_final_inr);

  const unmatB = gapBD.UNMATCHED_BANK || { count: 0, gap_final_inr: 0 };
  dom.gapCountUnmatchedB.textContent = `${unmatB.count} Rows`;
  dom.gapFinalUnmatchedB.textContent = formatINR(unmatB.gap_final_inr);

  renderFilterChips();
  applyFilters();
}

function renderFilterChips() {
  const anomalies = [
    { type: 'ALL', label: 'All Anomalies' },
    { type: 'TIMING_MONTH_END_CUTOFF', label: 'Month-End Cutoff' },
    { type: 'AMOUNT_FEE_DEDUCTION', label: 'MDR Fees (2%+GST)' },
    { type: 'BATCH_SETTLEMENT', label: 'Batches' },
    { type: 'DUPLICATE_PLATFORM', label: 'Platform Duplicates' },
    { type: 'DUPLICATE_BANK', label: 'Bank Duplicates' },
    { type: 'MISSING_IN_BANK', label: 'Missing in Bank' },
    { type: 'MISSING_IN_PLATFORM', label: 'Missing in Platform' },
    { type: 'AMOUNT_PARTIAL_SETTLEMENT', label: 'Partial Settled' },
    { type: 'REFUND_NO_ORIGINAL', label: 'Orphan Refunds' }
  ];

  dom.filterChips.innerHTML = anomalies
    .map(
      (a) => `
    <button class="chip ${state.filters.anomalyType === a.type ? 'active' : ''}" 
            onclick="selectAnomalyChip('${a.type}')">
      ${a.label}
    </button>
  `
    )
    .join('');
}

function selectAnomalyChip(atype) {
  state.filters.anomalyType = atype;
  state.currentPage = 1;
  renderFilterChips();
  applyFilters();
}

function filterByGapType(gapType) {
  state.filters.gapType = gapType;
  dom.gapTypeSelect.value = gapType;
  state.currentPage = 1;
  updateActiveGapCard(gapType);
  applyFilters();

  // Scroll to table smoothly
  document.querySelector('.table-section').scrollIntoView({ behavior: 'smooth' });
}

function updateActiveGapCard(activeGap) {
  document.querySelectorAll('.gap-card').forEach((card) => {
    if (card.dataset.gapFilter === activeGap) {
      card.classList.add('active-filter');
    } else {
      card.classList.remove('active-filter');
    }
  });
}

// -------------------------------------------------------------
// Filtering & Table Rendering
// -------------------------------------------------------------
function applyFilters() {
  if (!state.allGroups.length) {
    state.filteredGroups = [];
    renderTable();
    return;
  }

  state.filteredGroups = state.allGroups.filter((g) => {
    // Gap Type
    if (state.filters.gapType !== 'ALL' && g.gap_type !== state.filters.gapType) {
      return false;
    }

    // Status filter
    if (state.filters.status === 'ANOMALIES_ONLY' && !g.is_anomaly) return false;
    if (state.filters.status === 'CLEAN_ONLY' && g.is_anomaly) return false;

    // Anomaly Type Chip
    if (state.filters.anomalyType !== 'ALL' && g.anomaly_type !== state.filters.anomalyType) {
      return false;
    }

    // Method filter
    if (state.filters.method !== 'ALL') {
      const pMethods = g.platform_rows.map((r) => r.payment_method);
      if (!pMethods.includes(state.filters.method)) return false;
    }

    // Search query
    if (state.filters.search) {
      const q = state.filters.search;
      const matchP = g.platform_rows.some(
        (r) =>
          String(r.platform_txn_id).toLowerCase().includes(q) ||
          String(r.order_id).toLowerCase().includes(q) ||
          String(r.bank_ref || '').toLowerCase().includes(q) ||
          String(r.amount_inr).includes(q)
      );
      const matchB = g.bank_rows.some(
        (r) =>
          String(r.bank_txn_id).toLowerCase().includes(q) ||
          String(r.utr).toLowerCase().includes(q) ||
          String(r.narration).toLowerCase().includes(q) ||
          String(r.amount_inr).includes(q)
      );
      const matchMeta =
        g.group_id.toLowerCase().includes(q) ||
        g.anomaly_type.toLowerCase().includes(q) ||
        g.root_cause.toLowerCase().includes(q);

      if (!matchP && !matchB && !matchMeta) return false;
    }

    return true;
  });

  renderTable();
}

function renderTable() {
  const total = state.filteredGroups.length;
  dom.tableRecordCount.textContent = `Showing ${total} of ${state.allGroups.length} groups`;

  if (!total) {
    dom.tableBody.innerHTML = `
      <tr>
        <td colspan="12" class="empty-state">
          No transactions match your current filters. Try resetting filters.
        </td>
      </tr>
    `;
    dom.btnPrevPage.disabled = true;
    dom.btnNextPage.disabled = true;
    dom.pageInfo.textContent = 'Page 1 of 1';
    return;
  }

  const totalPages = Math.ceil(total / state.pageSize);
  if (state.currentPage > totalPages) state.currentPage = totalPages;

  const start = (state.currentPage - 1) * state.pageSize;
  const pageRows = state.filteredGroups.slice(start, start + state.pageSize);

  dom.btnPrevPage.disabled = state.currentPage <= 1;
  dom.btnNextPage.disabled = state.currentPage >= totalPages;
  dom.pageInfo.textContent = `Page ${state.currentPage} of ${totalPages}`;

  dom.tableBody.innerHTML = pageRows
    .map((g) => {
      const pFirst = g.platform_rows[0] || {};
      const bFirst = g.bank_rows[0] || {};

      const pRef = g.platform_ids.length > 1 ? `${g.platform_ids.length} txns (Batch)` : (pFirst.platform_txn_id || '-');
      const orderId = pFirst.order_id || (bFirst.narration && extractOrderFromNarr(bFirst.narration)) || '-';
      const method = pFirst.payment_method || '-';
      const pAmt = g.platform_effective_inr;

      const bRef = g.bank_ids.length > 1 ? `${g.bank_ids.length} credits (Dup)` : (bFirst.bank_txn_id || '-');
      const utr = bFirst.utr || '-';
      const bAmt = g.bank_effective_inr;

      const gap = g.gap_final_inr;
      const lag = g.settlement_lag_days !== null && g.settlement_lag_days !== undefined ? `T+${g.settlement_lag_days}` : '-';

      const tagClass = `gap-tag gap-tag-${g.gap_type.toLowerCase()}`;
      const gapClass = gap === 0 ? 'text-green' : gap > 0 ? 'text-amber' : 'text-red';

      return `
      <tr>
        <td class="font-mono"><strong>${g.group_id}</strong></td>
        <td><span class="${tagClass}">${g.gap_type}</span></td>
        <td><span title="${g.anomaly_type}">${cleanAnomalyType(g.anomaly_type)}</span></td>
        <td class="font-mono">${pRef}</td>
        <td class="font-mono">${orderId}</td>
        <td>${method}</td>
        <td class="font-mono">${formatINR(pAmt)}</td>
        <td class="font-mono" title="${utr}">${truncateStr(utr, 12)}</td>
        <td class="font-mono">${formatINR(bAmt)}</td>
        <td class="font-mono ${gapClass}"><strong>${formatINR(gap)}</strong></td>
        <td>${lag}</td>
        <td>
          <button class="btn btn-sm btn-ghost" onclick="openDetailModal('${g.group_id}')">
            Inspect
          </button>
        </td>
      </tr>
    `;
    })
    .join('');
}

function truncateStr(s, len) {
  if (!s || s === '-') return '-';
  return s.length > len ? s.substring(0, len) + '…' : s;
}

function extractOrderFromNarr(narr) {
  const m = narr.match(/ORD-2026-\d+/);
  return m ? m[0] : null;
}

function cleanAnomalyType(atype) {
  return atype
    .replace('TIMING_', '')
    .replace('AMOUNT_', '')
    .replace('STATUS_', '')
    .replace('REF_', '')
    .replace(/_/g, ' ');
}

// -------------------------------------------------------------
// Investigation Modal
// -------------------------------------------------------------
function openDetailModal(groupId) {
  const g = state.allGroups.find((x) => x.group_id === groupId);
  if (!g) return;

  dom.modalGroupId.textContent = g.group_id;
  dom.modalTitle.textContent = `${g.gap_type_label} — ${cleanAnomalyType(g.anomaly_type)}`;

  const pRowsHtml = g.platform_rows.length
    ? g.platform_rows
        .map(
          (p) => `
        <div class="modal-field"><span>Platform Txn ID:</span> <strong>${p.platform_txn_id}</strong></div>
        <div class="modal-field"><span>Order ID:</span> <strong>${p.order_id}</strong></div>
        <div class="modal-field"><span>Customer ID:</span> <strong>${p.customer_id}</strong></div>
        <div class="modal-field"><span>Amount (Gross):</span> <strong>${formatINR(p.amount_inr)}</strong></div>
        <div class="modal-field"><span>Status:</span> <strong>${p.status}</strong></div>
        <div class="modal-field"><span>Txn Type:</span> <strong>${p.txn_type}</strong></div>
        <div class="modal-field"><span>Created UTC:</span> <strong>${p.created_at_utc}</strong></div>
        <div class="modal-field"><span>Bank Ref:</span> <strong>${p.bank_ref || 'None'}</strong></div>
      `
        )
        .join('<hr style="border: 0.5px solid var(--border-color); margin: 8px 0;">')
    : '<p class="text-dim">No platform records exist for this group (Unmatched Bank / Spillover).</p>';

  const bRowsHtml = g.bank_rows.length
    ? g.bank_rows
        .map(
          (b) => `
        <div class="modal-field"><span>Bank Txn ID:</span> <strong>${b.bank_txn_id}</strong></div>
        <div class="modal-field"><span>UTR:</span> <strong>${b.utr}</strong></div>
        <div class="modal-field"><span>Amount:</span> <strong>${formatINR(b.amount_inr)}</strong></div>
        <div class="modal-field"><span>Credit / Debit:</span> <strong>${b.credit_debit}</strong></div>
        <div class="modal-field"><span>Status:</span> <strong>${b.status}</strong></div>
        <div class="modal-field"><span>Value Date:</span> <strong>${b.value_date_utc}</strong></div>
        <div class="modal-field"><span>Batch ID:</span> <strong>${b.batch_id || 'None'}</strong></div>
        <div class="modal-field"><span>Narration:</span> <strong style="font-size:0.74rem;">${b.narration}</strong></div>
      `
        )
        .join('<hr style="border: 0.5px solid var(--border-color); margin: 8px 0;">')
    : '<p class="text-dim">No bank record exists for this group (Unmatched Platform / Missing in Bank).</p>';

  dom.modalBody.innerHTML = `
    <div class="narrative-box">
      <div class="narrative-title">Root Cause & Economic Narrative</div>
      <p>${g.root_cause}</p>
    </div>

    <div class="action-box">
      <div class="action-title">Recommended Operational Resolution</div>
      <p>${g.expected_resolution}</p>
    </div>

    <div style="display:flex; justify-content:space-between; padding:12px 16px; background:var(--bg-elevated); border-radius:var(--radius-sm); margin:16px 0;">
      <div><span class="text-dim">Platform Effective:</span> <strong>${formatINR(g.platform_effective_inr)}</strong></div>
      <div><span class="text-dim">Bank Effective:</span> <strong>${formatINR(g.bank_effective_inr)}</strong></div>
      <div><span class="text-dim">Final Gap (P - B):</span> <strong class="${g.gap_final_inr === 0 ? 'text-green' : 'text-red'}">${formatINR(g.gap_final_inr)}</strong></div>
      <div><span class="text-dim">Settlement Lag:</span> <strong>${g.settlement_lag_days !== null ? `${g.settlement_lag_days} days` : 'N/A'}</strong></div>
    </div>

    <div class="modal-detail-grid">
      <div class="modal-pane">
        <h4>Platform Side (${g.platform_rows.length} row${g.platform_rows.length === 1 ? '' : 's'})</h4>
        ${pRowsHtml}
      </div>
      <div class="modal-pane">
        <h4>Bank Side (${g.bank_rows.length} row${g.bank_rows.length === 1 ? '' : 's'})</h4>
        ${bRowsHtml}
      </div>
    </div>
  `;

  dom.detailModal.classList.remove('hidden');
}

function closeModal() {
  dom.detailModal.classList.add('hidden');
}

// -------------------------------------------------------------
// Ground Truth Benchmark Modal
// -------------------------------------------------------------
async function openBenchmarkModal() {
  dom.benchmarkModal.classList.remove('hidden');
  dom.benchmarkLoading.classList.remove('hidden');
  dom.benchmarkContent.classList.add('hidden');

  try {
    const res = await fetch('/api/benchmark', { method: 'POST' });
    const data = await res.json();

    if (!data.success) {
      throw new Error(data.error || 'Benchmark failed.');
    }

    const bm = data.benchmark;

    const rowsHtml = Object.entries(bm.per_type_metrics)
      .map(([atype, m]) => {
        return `
        <tr>
          <td><strong>${atype}</strong></td>
          <td class="font-mono text-center">${m.ground_truth_count}</td>
          <td class="font-mono text-center">${m.reconciled_count}</td>
          <td class="font-mono text-center">${m.correct_matches}</td>
          <td class="font-mono text-center text-green"><strong>${(m.precision * 100).toFixed(1)}%</strong></td>
          <td class="font-mono text-center text-green"><strong>${(m.recall * 100).toFixed(1)}%</strong></td>
          <td class="font-mono text-center">${m.f1_score.toFixed(2)}</td>
        </tr>
      `;
      })
      .join('');

    dom.benchmarkContent.innerHTML = `
      <div class="benchmark-kpis">
        <div class="bm-card">
          <div class="bm-val">${(bm.type_accuracy * 100).toFixed(1)}%</div>
          <div class="bm-lbl">Anomaly Type Accuracy</div>
        </div>
        <div class="bm-card">
          <div class="bm-val">${(bm.category_accuracy * 100).toFixed(1)}%</div>
          <div class="bm-lbl">Category Accuracy</div>
        </div>
        <div class="bm-card">
          <div class="bm-val">${(bm.counterparts_accuracy * 100).toFixed(1)}%</div>
          <div class="bm-lbl">Counterparts Agreement</div>
        </div>
      </div>

      <p style="font-size:0.84rem; color:var(--text-muted); margin-bottom:14px;">
        Evaluated against <strong>${bm.total_records_evaluated} records</strong> in <code>ground_truth.csv</code> across all 24 injected anomaly types and clean matches.
      </p>

      <div class="table-container" style="max-height: 400px;">
        <table class="data-table">
          <thead>
            <tr>
              <th>Anomaly Scenario</th>
              <th class="text-center">Ground Truth Count</th>
              <th class="text-center">Reconciled Count</th>
              <th class="text-center">Correct Matches</th>
              <th class="text-center">Precision</th>
              <th class="text-center">Recall</th>
              <th class="text-center">F1 Score</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    `;

    dom.benchmarkLoading.classList.add('hidden');
    dom.benchmarkContent.classList.remove('hidden');
  } catch (err) {
    dom.benchmarkLoading.innerHTML = `<p class="text-red">Failed to run benchmark: ${err.message}</p>`;
  }
}

function closeBenchmarkModal() {
  dom.benchmarkModal.classList.add('hidden');
}

// Close modals on escape key or backdrop click
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeModal();
    closeBenchmarkModal();
  }
});

window.addEventListener('click', (e) => {
  if (e.target === dom.detailModal) closeModal();
  if (e.target === dom.benchmarkModal) closeBenchmarkModal();
});
