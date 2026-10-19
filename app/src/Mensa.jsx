import React from 'react';

const euro = value => `€${value.toFixed(2)}`;

// Today's menu, grouped by Mensa. English names and descriptions arrive once Gemma has written them.
export default function Mensa({ data }) {
  const menu = data.mensa_menu || [];
  if (!menu.length) return data.mensa.length ? <div className="mensa">{data.mensa.map((line, i) => <p key={i} className={line.startsWith('  -') ? 'meal-legacy' : 'canteen'}>{line.replace(/^\s*-\s*/, '')}</p>)}</div> : <p className="muted">No menu available for today.</p>;
  const pending = menu.some(canteen => canteen.meals.some(meal => !meal.name_en));
  return <div className="mensa">
    {menu.map(canteen => <section key={canteen.canteen} className="mensa-canteen" aria-label={canteen.canteen}>
      <h3 className="canteen">{canteen.canteen}</h3>
      {!canteen.open ? <p className="muted">Closed or no menu today.</p> : <ul className="meals">{canteen.meals.map((meal, i) => <li key={i} className="meal">
        <div className="meal-copy">
          <strong lang={meal.name_en ? undefined : 'de'}>{meal.name_en || meal.name}</strong>
          {meal.description && <p>{meal.description}</p>}
          <small lang={meal.name_en ? 'de' : undefined}>{meal.name_en ? meal.name : 'English description coming'}{meal.category ? ` · ${meal.category}` : ''}</small>
        </div>
        <span className="meal-price" aria-label={meal.student == null ? 'No student price listed' : `Student price ${euro(meal.student)}`}>{meal.student == null ? '—' : euro(meal.student)}<small>student</small></span>
      </li>)}</ul>}
    </section>)}
    {pending && <p className="mensa-note">{data.model.ready ? 'Gemma is writing English names and descriptions for the rest.' : 'Start Gemma in Settings for English names and descriptions.'}</p>}
  </div>;
}
