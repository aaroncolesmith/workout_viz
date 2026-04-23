/**
 * TrainingBlocks — create / view / compare user-defined training phases.
 *
 * Shows a timeline bar of all blocks + a metric card grid.
 * Clicking a block opens an editor. "New Block" opens a create form.
 */
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getBlocks, createBlock, updateBlock, deleteBlock } from '../utils/api';
import { formatPace, parseLocalDate } from '../utils/format';

const BLOCK_TYPES = ['base', 'build', 'peak', 'taper', 'race'];

const TYPE_META = {
  base:  { label: 'Base',  color: '#38bdf8', bg: 'rgba(56,189,248,0.12)'  },
  build: { label: 'Build', color: '#fb923c', bg: 'rgba(251,146,60,0.12)'  },
  peak:  { label: 'Peak',  color: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
  taper: { label: 'Taper', color: '#34d399', bg: 'rgba(52,211,153,0.12)'  },
  race:  { label: 'Race',  color: '#fbbf24', bg: 'rgba(251,191,36,0.12)'  },
};

const EMPTY_FORM = { name: '', block_type: 'base', start_date: '', end_date: '', notes: '' };

function blockDays(block) {
  try {
    const d0 = parseLocalDate(block.start_date);
    const d1 = parseLocalDate(block.end_date);
    return Math.max(1, Math.round((d1 - d0) / 86400000));
  } catch { return 1; }
}

function fmtPaceStr(paceMinMi) {
  if (!paceMinMi) return '—';
  return formatPace(paceMinMi) + ' /mi';
}

function fmtDelta(val, unit, goodNegative = false) {
  if (val == null) return null;
  const improved = goodNegative ? val < 0 : val > 0;
  const sign = val > 0 ? '+' : '';
  return { str: `${sign}${val}${unit}`, improved };
}

// ── Block editor form ────────────────────────────────────────────────────────

function BlockForm({ initial, onSave, onCancel, onDelete, saving }) {
  const [form, setForm] = useState(initial || EMPTY_FORM);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const isEdit = Boolean(initial?.id);

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(form);
  };

  const meta = TYPE_META[form.block_type] || TYPE_META.base;

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Block type selector */}
      <div>
        <label style={labelStyle}>Block Type</label>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {BLOCK_TYPES.map(t => {
            const m = TYPE_META[t];
            const active = form.block_type === t;
            return (
              <button
                key={t}
                type="button"
                onClick={() => set('block_type', t)}
                style={{
                  padding: '5px 14px',
                  borderRadius: 20,
                  border: `1px solid ${active ? m.color : 'var(--border-subtle)'}`,
                  background: active ? m.bg : 'transparent',
                  color: active ? m.color : 'var(--text-muted)',
                  fontWeight: active ? 600 : 400,
                  fontSize: '0.78rem',
                  cursor: 'pointer',
                }}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Name */}
      <div>
        <label style={labelStyle}>Name</label>
        <input
          required
          value={form.name}
          onChange={e => set('name', e.target.value)}
          placeholder={`e.g. Spring ${TYPE_META[form.block_type]?.label}`}
          style={inputStyle()}
        />
      </div>

      {/* Dates */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <label style={labelStyle}>Start Date</label>
          <input
            required
            type="date"
            value={form.start_date}
            onChange={e => set('start_date', e.target.value)}
            style={inputStyle()}
          />
        </div>
        <div>
          <label style={labelStyle}>End Date</label>
          <input
            required
            type="date"
            value={form.end_date}
            min={form.start_date}
            onChange={e => set('end_date', e.target.value)}
            style={inputStyle()}
          />
        </div>
      </div>

      {/* Notes */}
      <div>
        <label style={labelStyle}>Notes (optional)</label>
        <textarea
          value={form.notes || ''}
          onChange={e => set('notes', e.target.value)}
          placeholder="Goals, race target, coach notes…"
          rows={2}
          style={{ ...inputStyle(), resize: 'vertical' }}
        />
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between', marginTop: 4 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="submit"
            disabled={saving}
            style={{
              background: meta.color,
              color: '#0a0e1a',
              border: 'none',
              borderRadius: 8,
              padding: '8px 20px',
              fontWeight: 700,
              fontSize: '0.82rem',
              cursor: saving ? 'not-allowed' : 'pointer',
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Block'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            style={{
              background: 'transparent',
              border: '1px solid var(--border-subtle)',
              borderRadius: 8,
              padding: '8px 16px',
              color: 'var(--text-muted)',
              fontSize: '0.82rem',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
        </div>
        {isEdit && onDelete && (
          <button
            type="button"
            onClick={onDelete}
            style={{
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 8,
              padding: '8px 14px',
              color: '#ef4444',
              fontSize: '0.78rem',
              cursor: 'pointer',
            }}
          >
            Delete
          </button>
        )}
      </div>
    </form>
  );
}

// ── Block metric card ────────────────────────────────────────────────────────

function BlockCard({ block, onEdit }) {
  const meta = TYPE_META[block.block_type] || TYPE_META.base;
  const m = block.metrics;
  const d = block.delta;
  const days = blockDays(block);
  const weeks = (days / 7).toFixed(1);

  const volDelta  = fmtDelta(d?.volume_delta_pct, '%', true);
  const hrDelta   = fmtDelta(d?.hr_delta, ' bpm', false);

  return (
    <div
      className="glass-card"
      style={{
        padding: 'var(--space-md)',
        borderLeft: `3px solid ${meta.color}`,
        cursor: 'pointer',
        transition: 'border-color 0.15s',
      }}
      onClick={onEdit}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              fontSize: '0.62rem', fontWeight: 700, textTransform: 'uppercase',
              letterSpacing: '0.08em', color: meta.color,
              background: meta.bg, padding: '2px 8px', borderRadius: 10,
            }}>
              {meta.label}
            </span>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{weeks}w</span>
          </div>
          <div style={{ fontWeight: 700, fontSize: '0.95rem', marginTop: 5, color: 'var(--text-primary)' }}>
            {block.name}
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>
            {block.start_date} → {block.end_date}
          </div>
        </div>

        {/* CTL delta badge */}
        {m.ctl_delta != null && (
          <div style={{
            textAlign: 'right',
            background: m.ctl_delta >= 0 ? 'rgba(52,211,153,0.1)' : 'rgba(239,68,68,0.1)',
            border: `1px solid ${m.ctl_delta >= 0 ? 'rgba(52,211,153,0.25)' : 'rgba(239,68,68,0.25)'}`,
            borderRadius: 8,
            padding: '6px 10px',
          }}>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>CTL</div>
            <div style={{
              fontFamily: 'Manrope, sans-serif',
              fontSize: '0.85rem',
              fontWeight: 700,
              color: m.ctl_delta >= 0 ? '#34d399' : '#ef4444',
            }}>
              {m.ctl_delta >= 0 ? '+' : ''}{m.ctl_delta}
            </div>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>
              {m.ctl_start} → {m.ctl_end}
            </div>
          </div>
        )}
      </div>

      {/* Stat grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: d ? 10 : 0 }}>
        <Stat label="Activities" value={m.activity_count} />
        <Stat label="Weekly mi" value={m.avg_weekly_miles} />
        <Stat label="Avg Pace" value={fmtPaceStr(m.avg_pace)} />
        <Stat label="Avg HR" value={m.avg_hr ? `${m.avg_hr} bpm` : '—'} />
      </div>

      {/* Deltas vs previous same-type block */}
      {d && (
        <div style={{
          borderTop: '1px solid var(--border-subtle)', paddingTop: 8,
          display: 'flex', gap: 12, flexWrap: 'wrap',
        }}>
          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', marginRight: 4 }}>
            vs prev {meta.label}:
          </span>
          {d.pace_delta_str && (
            <DeltaPill value={d.pace_delta < 0} label={d.pace_delta_str} />
          )}
          {volDelta && (
            <DeltaPill value={volDelta.improved} label={`Volume ${volDelta.str}`} />
          )}
          {hrDelta && (
            <DeltaPill value={!hrDelta.improved} label={`HR ${hrDelta.str}`} />
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'Manrope, sans-serif' }}>
        {value ?? '—'}
      </div>
    </div>
  );
}

function DeltaPill({ value: improved, label }) {
  return (
    <span style={{
      fontSize: '0.68rem',
      color: improved ? '#34d399' : '#fb7185',
      background: improved ? 'rgba(52,211,153,0.08)' : 'rgba(251,113,133,0.08)',
      border: `1px solid ${improved ? 'rgba(52,211,153,0.2)' : 'rgba(251,113,133,0.2)'}`,
      padding: '2px 8px',
      borderRadius: 10,
    }}>
      {improved ? '↑' : '↓'} {label}
    </span>
  );
}

// ── Timeline bar ─────────────────────────────────────────────────────────────

function BlockTimeline({ blocks, onSelect }) {
  if (!blocks.length) return null;

  const sorted = [...blocks].sort((a, b) => a.start_date.localeCompare(b.start_date));
  const minDate = parseLocalDate(sorted[0].start_date);
  const maxDate = parseLocalDate(sorted[sorted.length - 1].end_date);
  const totalMs = Math.max(1, maxDate - minDate);

  return (
    <div style={{ marginBottom: 'var(--space-xl)' }}>
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>
        Training Timeline
      </div>
      <div style={{ position: 'relative', height: 36, background: 'rgba(255,255,255,0.03)', borderRadius: 8, overflow: 'hidden' }}>
        {sorted.map(block => {
          const meta = TYPE_META[block.block_type] || TYPE_META.base;
          const left = (parseLocalDate(block.start_date) - minDate) / totalMs * 100;
          const width = Math.max(0.5, (parseLocalDate(block.end_date) - parseLocalDate(block.start_date)) / totalMs * 100);
          return (
            <div
              key={block.id}
              title={`${block.name} (${block.start_date} – ${block.end_date})`}
              onClick={() => onSelect(block)}
              style={{
                position: 'absolute',
                left: `${left}%`,
                width: `${width}%`,
                height: '100%',
                background: meta.bg,
                borderLeft: `2px solid ${meta.color}`,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                paddingLeft: 6,
                overflow: 'hidden',
              }}
            >
              <span style={{ fontSize: '0.65rem', color: meta.color, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {block.name}
              </span>
            </div>
          );
        })}
      </div>
      {/* Date labels */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
        <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{sorted[0].start_date}</span>
        <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{sorted[sorted.length - 1].end_date}</span>
      </div>
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────

export default function TrainingBlocks() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(null);   // null | 'new' | block object
  const [saving, setSaving] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['blocks'],
    queryFn: getBlocks,
    staleTime: 60_000,
  });

  const blocks = data?.blocks || [];

  const invalidate = () => qc.invalidateQueries({ queryKey: ['blocks'] });

  const handleSave = async (form) => {
    setSaving(true);
    try {
      if (editing === 'new') {
        await createBlock(form);
      } else {
        await updateBlock(editing.id, form);
      }
      await invalidate();
      setEditing(null);
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!editing?.id) return;
    if (!confirm(`Delete "${editing.name}"?`)) return;
    setSaving(true);
    try {
      await deleteBlock(editing.id);
      await invalidate();
      setEditing(null);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ marginBottom: 'var(--space-xl)' }}>
      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-lg)' }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>Training Blocks</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
            Define training phases to track block-over-block progress
          </div>
        </div>
        <button
          onClick={() => setEditing('new')}
          style={{
            background: 'rgba(56,189,248,0.1)',
            border: '1px solid rgba(56,189,248,0.3)',
            borderRadius: 8,
            padding: '7px 16px',
            color: '#38bdf8',
            fontWeight: 600,
            fontSize: '0.8rem',
            cursor: 'pointer',
          }}
        >
          + New Block
        </button>
      </div>

      {/* Create / Edit form */}
      {editing && (
        <div className="glass-card" style={{ padding: 'var(--space-md)', marginBottom: 'var(--space-lg)' }}>
          <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: 14, color: 'var(--text-primary)' }}>
            {editing === 'new' ? 'New Training Block' : `Edit: ${editing.name}`}
          </div>
          <BlockForm
            initial={editing === 'new' ? EMPTY_FORM : editing}
            onSave={handleSave}
            onCancel={() => setEditing(null)}
            onDelete={editing !== 'new' ? handleDelete : null}
            saving={saving}
          />
        </div>
      )}

      {isLoading && (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: 'var(--space-md)' }}>
          Loading blocks…
        </div>
      )}

      {!isLoading && blocks.length === 0 && !editing && (
        <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center' }}>
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>No training blocks yet</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 'var(--space-md)' }}>
            Create blocks to track Base → Build → Peak → Taper phases and compare block-over-block fitness.
          </div>
          <button
            onClick={() => setEditing('new')}
            style={{
              background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.3)',
              borderRadius: 8, padding: '8px 20px', color: '#38bdf8',
              fontWeight: 600, fontSize: '0.82rem', cursor: 'pointer',
            }}
          >
            Create First Block
          </button>
        </div>
      )}

      {blocks.length > 0 && (
        <>
          <BlockTimeline blocks={blocks} onSelect={b => setEditing(b)} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 'var(--space-md)' }}>
            {blocks.map(b => (
              <BlockCard key={b.id} block={b} onEdit={() => setEditing(b)} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── Style helpers ─────────────────────────────────────────────────────────────

const labelStyle = {
  display: 'block',
  fontSize: '0.68rem',
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 5,
};

function inputStyle() {
  return {
    width: '100%',
    background: 'rgba(255,255,255,0.04)',
    border: `1px solid rgba(255,255,255,0.1)`,
    borderRadius: 8,
    padding: '8px 12px',
    color: 'var(--text-primary)',
    fontSize: '0.85rem',
    outline: 'none',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
  };
}
