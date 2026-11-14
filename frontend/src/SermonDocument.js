import React from 'react';

function fmtTime(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
}

export function fmtDate(value) {
  if (!value) return '';
  const d = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  return isNaN(d) ? String(value) : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}

function At({ seconds, onSeek }) {
  const s = Number(seconds);
  if (!(s > 0) || !onSeek) return null;
  return <button className="time-link" onClick={() => onSeek(s)}>▶ {fmtTime(s)}</button>;
}

function Section({ n, title, children }) {
  return (
    <section className="doc-section">
      <h3 className="doc-h"><span className="doc-n">{n}.</span> {title}</h3>
      {children}
    </section>
  );
}

// The 11-section sermon documentation. Falls back gracefully for sermons curated before v2.
export function documentView(s) {
  const intro = s.introduction || {};
  const sections = (s.full_notes || []).filter(x => x && typeof x === 'object');
  let points = (s.main_points || []).filter(p => p && p.point);
  if (!points.length) points = sections.filter(x => x.section_title).map(x => ({ point: x.section_title, summary: '', start_seconds: x.start_seconds }));
  let explanations = (s.explanations || []).filter(Boolean);
  if (!explanations.length) explanations = (s.theological_depths || []).map(t => ({ title: t.concept, explanation: t.full_explanation }));
  const verses = (s.all_bible_verses || []).filter(Boolean);
  let takeaways = (s.key_takeaways || []).filter(Boolean);
  if (!takeaways.length) takeaways = points.map(p => p.point).slice(0, 6);
  return {
    info: [['Preacher', s.preacher], ['Church', s.church_name], ['Date', fmtDate(s.sermon_date)],
      ['Main text', s.main_text || verses[0]?.reference], ['Topic', intro.topic || s.main_theme], ['Series', s.series]],
    overview: intro.overview || s.summary || '',
    central: s.central_message || s.main_theme || '',
    points, sections, verses, explanations, takeaways,
    illustrations: sections.flatMap(x => (x.illustrations || []).map(ill => ({ ...ill, section: x.section_title }))),
    quotes: s.notable_quotes || [],
    applications: s.practical_applications || [],
    questions: s.study_questions || [],
    group: (s.sermon_start_info || {}).small_group_guide || {},
    prayers: s.prayer_points || [],
  };
}

export default function SermonDocument({ sermon, onSeek }) {
  const d = documentView(sermon);
  const infoRows = d.info.filter(([, v]) => v);
  const group = d.group || {};
  return (
    <article className="sermon-doc">
      <header className="doc-title-block">
        <h2 className="doc-title">{(sermon.title || 'Sermon').toUpperCase()}</h2>
        <p className="doc-sub">Sermon documentation{sermon.sermon_date ? ` · ${fmtDate(sermon.sermon_date)}` : ''}</p>
      </header>

      <Section n={1} title="Sermon information">
        <table className="doc-table"><tbody>
          {infoRows.map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}
        </tbody></table>
      </Section>

      {d.overview && <Section n={2} title="Sermon overview">
        {d.overview.split(/\n\s*\n/).map((p, i) => <p key={i} className="body">{p}</p>)}
      </Section>}

      {d.central && <Section n={3} title="Central message">
        <blockquote className="doc-central">{d.central}</blockquote>
      </Section>}

      {d.points.length > 0 && <Section n={4} title="Main teaching points">
        <ol className="doc-points">
          {d.points.map((p, i) => (
            <li key={i}>
              <p className="doc-point-title">Point {i + 1}: {p.point} <At seconds={p.start_seconds} onSeek={onSeek} /></p>
              {p.summary && <p className="body small">{p.summary}</p>}
            </li>
          ))}
        </ol>
        {d.sections.some(x => x.full_teaching) && (
          <details className="doc-details" open>
            <summary>Full teaching, point by point</summary>
            {d.sections.map((x, i) => (
              <div key={i} className="doc-teaching">
                <h4 className="doc-h4">{x.section_number || i + 1}. {x.section_title} <At seconds={x.start_seconds} onSeek={onSeek} /></h4>
                {x.full_teaching && <p className="body pre">{x.full_teaching}</p>}
                {(x.scriptures_in_this_section || []).map((v, j) => (
                  <div key={j} className="scripture">
                    <p className="ref">{v.reference}</p>
                    {v.text_as_used && <p className="body italic">"{v.text_as_used}"</p>}
                    {v.how_preacher_used_it && <p className="body small">{v.how_preacher_used_it}</p>}
                  </div>
                ))}
                {x.section_application && <p className="body small"><strong>Application:</strong> {x.section_application}</p>}
              </div>
            ))}
          </details>
        )}
      </Section>}

      {d.verses.length > 0 && <Section n={5} title="Scriptural references">
        <table className="doc-table refs">
          <thead><tr><th>Reference</th><th>Context</th><th>Relevance</th></tr></thead>
          <tbody>{d.verses.map((v, i) => (
            <tr key={i}>
              <td className="ref-cell">{v.reference} <At seconds={v.start_seconds} onSeek={onSeek} />
                {v.text_quoted && <div className="verse-text-small">"{v.text_quoted}"</div>}</td>
              <td>{v.sermon_context}</td>
              <td>{v.relevance}{(v.cross_references || []).length > 0 && <div className="soft">See also: {v.cross_references.join(', ')}</div>}</td>
            </tr>
          ))}</tbody>
        </table>
      </Section>}

      {d.explanations.length > 0 && <Section n={6} title="Important explanations and revelations">
        {d.explanations.map((e, i) => (
          <div key={i} className="callout purple">
            <p className="ref" style={{ color: 'var(--purple)' }}>{e.title}{e.kind && <span className="kind">{e.kind}</span>} <At seconds={e.start_seconds} onSeek={onSeek} /></p>
            <p className="body">{e.explanation}</p>
            {(e.scriptures || []).length > 0 && <p className="soft">Scriptures: {e.scriptures.join(', ')}</p>}
          </div>
        ))}
      </Section>}

      {(d.illustrations.length > 0 || d.quotes.length > 0) && <Section n={7} title="Illustrations and notable quotes">
        {d.illustrations.map((ill, i) => (
          <div key={i} className="callout gold">
            <p className="mini-label">Illustration: {ill.title}</p>
            <p className="body">{ill.full_story}</p>
            {ill.spiritual_point && <p className="point">Point: {ill.spiritual_point}</p>}
          </div>
        ))}
        {d.quotes.map((q, i) => (
          <div key={i} style={{ marginBottom: 12 }}>
            <blockquote className="quote">"{q.quote}"</blockquote>
            <p className="quote-context">{q.context} <At seconds={q.start_seconds} onSeek={onSeek} /></p>
          </div>
        ))}
      </Section>}

      {d.applications.length > 0 && <Section n={8} title="Practical applications">
        <ul className="doc-list">
          {d.applications.map((a, i) => (
            <li key={i}><strong>{a.application || a}</strong>
              {a.why_it_matters && <span className="body small"> {a.why_it_matters}</span>}
              {a.how_to_do_it && <div className="body small">How: {a.how_to_do_it}</div>}</li>
          ))}
        </ul>
        {sermon.weekly_challenge && <div className="callout gold"><p className="mini-label">This week's challenge</p><p className="body">{sermon.weekly_challenge}</p></div>}
      </Section>}

      {(d.questions.length > 0 || group.discussion) && <Section n={9} title="Reflection and discussion questions">
        <ol className="doc-list numbered">
          {d.questions.map((q, i) => (
            <li key={i}>{q.question || q}{(q.for === 'group' || q.for === 'personal') && <span className="kind">{q.for}</span>}
              {q.what_to_think_about && <div className="soft">{q.what_to_think_about}</div>}</li>
          ))}
        </ol>
        {(group.icebreaker || (group.discussion || []).length > 0) && (
          <div className="callout cream">
            <p className="mini-label">For small groups and house fellowships</p>
            {group.icebreaker && <p className="body small"><strong>Icebreaker:</strong> {group.icebreaker}</p>}
            {(group.discussion || []).map((q, i) => <p key={i} className="body small">• {q}</p>)}
            {group.activity && <p className="body small"><strong>Activity:</strong> {group.activity}</p>}
            {group.closing_prayer && <p className="body small"><strong>Closing prayer:</strong> {group.closing_prayer}</p>}
          </div>
        )}
      </Section>}

      {d.prayers.length > 0 && <Section n={10} title="Prayer points">
        <ol className="doc-list numbered">
          {d.prayers.map((p, i) => <li key={i}>{p.point || p}{p.scripture_basis && <span className="soft"> ({p.scripture_basis})</span>}</li>)}
        </ol>
      </Section>}

      {d.takeaways.length > 0 && <Section n={11} title="Key takeaways">
        <ul className="doc-takeaways">{d.takeaways.map((t, i) => <li key={i}>{t}</li>)}</ul>
      </Section>}
    </article>
  );
}
