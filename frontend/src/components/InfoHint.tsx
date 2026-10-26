import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type MouseEvent,
} from "react";
import { Info } from "lucide-react";
import "./InfoHint.css";

export type InfoHintProps = {
  /** Label of the term being explained (used for aria-label) */
  label?: string;
  /** Plain-language explanation text */
  text?: string;
  /** Rich explanation content (alternative to text) */
  children?: ReactNode;
  /** Optional className for the wrapper */
  className?: string;
};

export function InfoHint({ label, text, children, className }: InfoHintProps) {
  const [open, setOpen] = useState(false);
  const [alignment, setAlignment] = useState<"center" | "left" | "right">("center");
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const tooltipId = useId();

  const content = text ?? children;
  if (!content) return null;

  // Check viewport boundaries when opened to prevent horizontal clipping
  useEffect(() => {
    if (!open || !wrapperRef.current) return;
    const rect = wrapperRef.current.getBoundingClientRect();
    const viewportWidth = window.innerWidth;

    if (rect.left < 130) {
      setAlignment("left");
    } else if (viewportWidth - rect.right < 130) {
      setAlignment("right");
    } else {
      setAlignment("center");
    }
  }, [open]);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  // Close on click / tap outside
  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  const toggle = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    setOpen((prev) => !prev);
  };

  const handleMouseEnter = () => setOpen(true);
  const handleMouseLeave = () => setOpen(false);
  const handleFocus = () => setOpen(true);
  const handleBlur = () => setOpen(false);

  const alignClass =
    alignment === "right" ? " align-right" : alignment === "left" ? " align-left" : "";

  return (
    <span
      className={`info-hint-wrapper${alignClass}${className ? ` ${className}` : ""}`}
      ref={wrapperRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        ref={buttonRef}
        type="button"
        className={`info-hint-button${open ? " is-active" : ""}`}
        aria-label={label ? `Explanation for ${label}` : "More information"}
        aria-describedby={open ? tooltipId : undefined}
        aria-expanded={open}
        onClick={toggle}
        onFocus={handleFocus}
        onBlur={handleBlur}
      >
        <Info className="info-hint-icon" aria-hidden="true" />
      </button>

      <div
        id={tooltipId}
        role="tooltip"
        className={`info-hint-popover${open ? " is-open" : ""}`}
        aria-hidden={!open}
      >
        {content}
      </div>
    </span>
  );
}

export function LabelWithHint({
  label,
  hint,
  hintLabel,
  className,
}: {
  label: ReactNode;
  hint: string;
  hintLabel?: string;
  className?: string;
}) {
  const ariaLabel =
    hintLabel ?? (typeof label === "string" ? label : undefined);

  return (
    <span className={`label-with-hint${className ? ` ${className}` : ""}`}>
      {label}
      <InfoHint label={ariaLabel} text={hint} />
    </span>
  );
}
