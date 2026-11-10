// A text box with a themed suggestion list: a "combobox".
// Replaces <datalist>, whose popup the browser draws itself and CSS can't style.
//
// You can still type any name (a new payee is fine). The list only offers what you've used.
// Keys: ↓/↑ move, Enter picks, Escape closes. Mouse: click a name.

import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type Ref } from "react";

import { suggestPayees } from "../lib/payees";

type Props = {
  value: string;
  onChange: (name: string) => void;
  names: string[];
  inputRef?: Ref<HTMLInputElement>;
  placeholder?: string;
  ariaLabel?: string;
};

export function PayeeInput({ value, onChange, names, inputRef, placeholder, ariaLabel }: Props) {
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1); // highlighted row; -1 = none

  const suggestions = useMemo(() => suggestPayees(names, value), [names, value]);
  // Don't offer the exact name that's already typed: there's nothing left to pick.
  const pointless = suggestions.length === 1 && suggestions[0].toLowerCase() === value.trim().toLowerCase();
  const showing = open && suggestions.length > 0 && !pointless;

  // Keep the highlighted row in view when arrowing through a long list.
  useEffect(() => {
    listRef.current?.querySelector(".active")?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function pick(name: string) {
    onChange(name);
    setOpen(false);
    setActive(-1);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); // stop the cursor jumping to the start/end of the text
      if (!showing) return setOpen(true);
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + step + suggestions.length) % suggestions.length);
    } else if (e.key === "Enter" && showing && active >= 0) {
      e.preventDefault(); // pick the name instead of submitting the form
      pick(suggestions[active]);
    } else if (e.key === "Escape" && showing) {
      e.stopPropagation(); // close the list, not the side panel
      setOpen(false);
    }
  }

  return (
    <div className="combo">
      <input
        ref={inputRef}
        className="input"
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={showing}
        aria-controls={listId}
        aria-activedescendant={showing && active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {showing && (
        <ul className="combo-list" id={listId} role="listbox" ref={listRef}>
          {suggestions.map((name, i) => (
            <li
              key={name}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : undefined}
              // mousedown, not click: click fires after the input's blur has closed the list.
              onMouseDown={(e) => {
                e.preventDefault();
                pick(name);
              }}
              onMouseEnter={() => setActive(i)}
            >
              <Highlight text={name} query={value.trim()} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Lights up the first place `query` appears in `text`. */
function Highlight({ text, query }: { text: string; query: string }) {
  const at = query ? text.toLowerCase().indexOf(query.toLowerCase()) : -1;
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + query.length)}</mark>
      {text.slice(at + query.length)}
    </>
  );
}
