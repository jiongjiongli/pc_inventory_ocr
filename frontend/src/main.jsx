import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Unable to complete the request.');
  return data;
}

function InventoryDownload() {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');
  async function download() {
    setDownloading(true); setError('');
    try {
      const response = await fetch('/api/pc-inventory.xlsx', {cache: 'no-store'});
      if (!response.ok) throw new Error('Unable to generate inventory. Please try again.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = 'pc-inventory.xlsx';
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {setError(error.message);}
    finally {setDownloading(false);}
  }
  return <div className="inventory-download"><button className="button export-button" onClick={download} disabled={downloading}>{downloading ? 'Generating Excel…' : 'Download pc-inventory.xlsx ↓'}</button>{error && <p className="hint" role="alert">{error}</p>}</div>;
}

function formatOcrTime(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  return [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60]
    .map(value => String(value).padStart(2, '0')).join(':');
}

function RecognizedSku({pc}) {
  const text = pc.ocr_text || '';
  const candidates = new Set([
    ...Array.from(text.matchAll(/\bSKU\s*[:#：-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)/gi), match => match[1].toUpperCase()),
    ...Array.from(text.matchAll(/\bCLP[A-Za-z0-9._/-]*\b/gi), match => match[0].toUpperCase()),
  ]);
  const sku = pc.ocr_status === 'completed'
    ? candidates.size === 1 ? [...candidates][0] : candidates.size > 1 ? 'Multiple values detected' : 'Not detected'
    : pc.ocr_status === 'pending' || pc.ocr_status === 'processing' ? 'Awaiting OCR' : 'Not detected';
  const matchingLines = (pc.ocr_lines || []).filter(line => {
    const values = [
      ...Array.from(line.text.matchAll(/\bSKU\s*[:#：-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)/gi), match => match[1].toUpperCase()),
      ...Array.from(line.text.matchAll(/\bCLP[A-Za-z0-9._/-]*\b/gi), match => match[0].toUpperCase()),
    ];
    return candidates.size === 1 && values.includes(sku);
  });
  const confidence = matchingLines.length ? Math.min(...matchingLines.map(line => line.confidence)) : null;
  return <div className="sku-review"><p className="recognized-sku"><strong>SKU:</strong> {sku}</p><p className="hint">SKU line confidence: {confidence != null ? `${(confidence * 100).toFixed(1)}%` : 'Unavailable'}</p>{candidates.size > 1 && <p className="hint">Candidates: {[...candidates].join(', ')}</p>}</div>;
}

function OcrResults({pc}) {
  const messages = {pending: 'Queued for OCR', processing: 'Processing OCR…', empty: 'No readable text detected', failed: 'Text extraction failed. Try a clearer photo.'};
  return <div className="ocr-results"><h4>Check rotated image &amp; SKU</h4><div className="ocr-review">{pc.rotated_image_url ? <a href={`${pc.rotated_image_url}?photo=${encodeURIComponent(pc.photo)}`} target="_blank" rel="noreferrer" aria-label="Open full-size rotated box image"><img className="rotated-result-image" src={`${pc.rotated_image_url}?photo=${encodeURIComponent(pc.photo)}`} alt="Rotated box photo used for OCR" loading="lazy"/></a> : <p className="hint">{['completed', 'empty'].includes(pc.ocr_status) ? 'Rotated image unavailable. Reprocess this photo to generate it.' : 'Rotated image will appear after OCR.'}</p>}{pc.rotated_180_image_url && <figure className="rotated-preview"><figcaption>Rotated image + 180°</figcaption><a href={`${pc.rotated_180_image_url}?photo=${encodeURIComponent(pc.photo)}`} target="_blank" rel="noreferrer" aria-label="Open full-size box image rotated an additional 180 degrees"><img className="rotated-result-image" src={`${pc.rotated_180_image_url}?photo=${encodeURIComponent(pc.photo)}`} alt="Box photo rotated an additional 180 degrees" loading="lazy"/></a></figure>}<RecognizedSku pc={pc}/></div><p className="hint">OCR time: {pc.ocr_status === 'processing' ? 'Processing…' : pc.ocr_status === 'pending' ? 'Waiting in queue' : pc.ocr_duration_seconds != null ? formatOcrTime(pc.ocr_duration_seconds) : 'Not recorded for this photo'}</p>{pc.ocr_json_url && <a className="json-download" href={pc.ocr_json_url} download>Download OCR JSON ↓</a>}<p role="status">{messages[pc.ocr_status] || (pc.ocr_status === 'completed' ? 'OCR complete' : '')}</p>{pc.ocr_confidence != null && <p className="hint">Average confidence: {(pc.ocr_confidence * 100).toFixed(1)}%</p>}</div>;
}

function Editor({pc, onCancel, onSaved}) {
  const [values, setValues] = useState({row_number: pc?.row_number ?? '', column_number: pc?.column_number ?? '', pc_type: pc?.pc_type ?? 'MiniPC'});
  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!photo) {setPreview(null); return;}
    const url = URL.createObjectURL(photo); setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo, pc]);
  function change(event) {setValues({...values, [event.target.name]: event.target.value});}
  function choose(event) {
    const file = event.target.files[0];
    if (file?.size > 16 * 1024 * 1024) {setError('Please choose a photo smaller than 16 MB.'); event.target.value = ''; return;}
    setError(''); setPhoto(file || null);
  }
  async function save(event) {
    event.preventDefault(); setSaving(true); setError('');
    const form = new FormData();
    Object.entries(values).forEach(([key, value]) => form.append(key, value));
    if (photo) form.append('photo', photo);
    try {await api(pc ? `/api/pcs/${pc.id}` : '/api/pcs', {method: pc ? 'PUT' : 'POST', body: form}); onSaved();}
    catch (error) {setError(error.message);}
    finally {setSaving(false);}
  }
  return <><button className="back text-button" onClick={onCancel}>← Back to shelf</button><div className="form-heading"><p className="eyebrow">YOUR PC INVENTORY</p><h1>{pc ? 'Edit PC' : 'Add a PC'}<span>.</span></h1><p className="subtitle">A location and a photo. Everything you need to find it again.</p></div><form className="editor" onSubmit={save}>
    {error && <div className="notice" role="alert">{error}</div>}
    <fieldset disabled={saving} className="editor-fields"><div className="form-section"><h2><span className="step">01</span> Shelf location</h2><div className="fields">{[['row_number','Row number'],['column_number','Column number']].map(([name,label]) => <label key={name}>{label}<input name={name} type="number" inputMode="numeric" min="1" max="9999" value={values[name]} onChange={change} required /></label>)}</div><fieldset><legend>PC type</legend><div className="types">{['MiniPC','Laptop'].map(kind => <label className="type-choice" key={kind}><input type="radio" name="pc_type" value={kind} checked={values.pc_type === kind} onChange={change}/><span>{kind}</span></label>)}</div></fieldset></div>
    <div className="form-section"><h2><span className="step">02</span> Box photo</h2><p className="hint">Take a photo or choose one from your phone. Maximum upload: 16 MB.</p><div className="upload">{preview && <img src={preview} alt="PC box photo preview"/>}<div className="upload-label"><span>＋</span><strong>{pc ? 'Replace photo' : 'Add a box photo'}</strong><small>Use your camera or choose a saved photo</small></div><div className="photo-actions"><label className="photo-picker">Take photo<input aria-label="Take a box photo" type="file" accept="image/*" capture="environment" onChange={choose}/></label><label className="photo-picker">Choose photo<input aria-label="Choose a box photo" type="file" accept="image/*" onChange={choose}/></label></div></div><p className="hint">{photo ? photo.name : pc ? 'Your current photo is kept unless you select a replacement.' : 'A box photo is required.'}</p></div>
    {pc && <div className="form-section"><OcrResults pc={pc}/><p className="hint">Results update automatically when you replace the photo.</p></div>}<div className="form-actions"><button type="button" className="back text-button" onClick={onCancel}>Cancel</button><button type="submit" className="button" disabled={saving || (!pc && !photo)}>{saving ? 'Saving…' : pc ? 'Save changes ↗' : 'Add to shelf ↗'}</button></div></fieldset></form></>;
}

function App() {
  const [atPageEnd, setAtPageEnd] = useState(false);
  useEffect(() => {
    const update = () => setAtPageEnd(window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 48);
    window.addEventListener('scroll', update, {passive: true});
    window.addEventListener('resize', update);
    const observer = new ResizeObserver(update);
    observer.observe(document.body);
    update();
    return () => {
      window.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
      observer.disconnect();
    };
  }, []);
  const [pcs, setPcs] = useState([]), [loading, setLoading] = useState(true), [error, setError] = useState(''), [editor, setEditor] = useState(null), [notice, setNotice] = useState('');
  async function load() {setLoading(true); setError(''); try {setPcs(await api('/api/pcs'));} catch(error) {setError(error.message);} finally {setLoading(false);}}
  useEffect(() => {
    load();
    const timer = setInterval(async () => {
      try {setPcs(await api('/api/pcs'));} catch (error) { /* Keep the last inventory during a temporary interruption. */ }
    }, 3000);
    return () => clearInterval(timer);
  }, []);
  async function remove(pc) {
    if (!window.confirm(`Delete overall PC ${pcs.findIndex(record => record.id === pc.id) + 1} and its photo?`)) return;
    try {await api(`/api/pcs/${pc.id}`, {method: 'DELETE'}); setEditor(null); setNotice('PC deleted.'); await load();}
    catch (error) {setError(error.message);}
  }
  function open(pc) {setEditor({pc}); setNotice(''); window.scrollTo(0,0);}
  function saved() {setNotice(editor.pc ? 'PC updated.' : 'PC added to your shelf.'); setEditor(null); load(); window.scrollTo(0,0);}
  const rows = [...new Set(pcs.map(pc => pc.row_number))];
  return <><header><a className="brand" href="/" onClick={event => {event.preventDefault(); setEditor(null);}}><span>▦</span> SHELF / PC INVENTORY</a><span className="tagline">A place for every PC.</span></header><main>{notice && <div className="notice" role="status">{notice}</div>}{editor ? <Editor key={editor.pc?.id || 'new'} pc={editor.pc ? (pcs.find(pc => pc.id === editor.pc.id) || editor.pc) : null} onCancel={() => setEditor(null)} onSaved={saved}/> : <><div className="heading"><div><p className="eyebrow">YOUR INVENTORY, ORGANIZED</p><h1>Stacked Shelf PCs<span>.</span></h1><p className="subtitle">Find the right box. Right where you left it.</p></div><div className="inventory-actions"><InventoryDownload/><button className="button" onClick={() => open(null)}>＋ Add a PC</button></div></div><div className="stats">{[[pcs.length,'Total PCs'],[pcs.filter(pc => pc.pc_type === 'MiniPC').length,'MiniPCs'],[pcs.filter(pc => pc.pc_type === 'Laptop').length,'Laptops']].map(([count,label]) => <div key={label}><strong>{count}</strong><span>{label}</span></div>)}</div><div className="section-heading"><h2>On the shelf</h2><span>Sorted by row & column</span></div>{loading ? <p role="status">Loading your shelf…</p> : error ? <div className="notice" role="alert">{error} <button className="text-button" onClick={load}>Try again</button></div> : pcs.length ? rows.map(row => <section key={row}><h3 className="row-label">SHELF ROW {row}</h3><div className="grid">{pcs.filter(pc => pc.row_number === row).map((pc, rowIndex) => <article className="card" id={`pc-${pc.id}`} key={pc.id}><h3 className="pc-image-heading">Row {row} / Column {pc.column_number} / PC {pcs.filter(record => record.row_number === row && record.column_number === pc.column_number).findIndex(record => record.id === pc.id) + 1}</h3><div className="card-body"><div className="pc-details"><p><strong>PC type:</strong> {pc.pc_type}</p></div><p className="hint">Overall PC {pcs.findIndex(record => record.id === pc.id) + 1} / PC {rowIndex + 1} in this row</p><OcrResults pc={pc}/><div className="card-bottom"><div className="item-actions"><button className="text-button" onClick={() => open(pc)}>Edit PC ↗</button><button className="text-button delete-button" onClick={() => remove(pc)}>Delete PC</button></div></div></div></article>)}</div></section>) : <div className="empty"><div className="empty-icon">▦</div><h2>Your shelf starts here</h2><p>Add a PC, mark its location, and snap a photo of the box.</p><button className="button" onClick={() => open(null)}>＋ Add your first PC</button></div>}</>}</main>{!editor && <div className="floating-controls">{pcs.length > 0 && <button className="button last-pc-button" onClick={() => window.scrollTo({top: atPageEnd ? 0 : document.documentElement.scrollHeight, behavior: 'smooth'})}>{atPageEnd ? '↑ Go to First PC' : 'Go to Last PC ↓'}</button>}<button className="button" onClick={() => open(null)}>＋ Add a PC</button></div>}<footer>Stacked Shelf PCs <span>Keep your inventory in view.</span></footer></>;
}
createRoot(document.getElementById('root')).render(<App/>);
