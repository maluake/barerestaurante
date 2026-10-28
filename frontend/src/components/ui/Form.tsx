import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import clsx from "clsx";

export function Field({ label, hint, error, children, className, htmlFor, required }: {
  label?: ReactNode; hint?: ReactNode; error?: string; children: ReactNode; className?: string; htmlFor?: string; required?: boolean;
}) {
  return (
    <div className={clsx("space-y-1.5", className)}>
      {label && (
        <label htmlFor={htmlFor} className="block text-sm font-medium text-stone-700">
          {label}
          {required && <span className="ml-0.5 text-red-700" aria-hidden>*</span>}
        </label>
      )}
      {children}
      {error ? <p className="text-xs font-medium text-red-700" role="alert">{error}</p> : hint ? <p className="text-xs text-stone-500">{hint}</p> : null}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & { label?: ReactNode; hint?: ReactNode; error?: string; suffix?: ReactNode };

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ label, hint, error, className, suffix, id, required, ...rest }, ref) {
  const auto = useId();
  const inputId = id || auto;
  const input = (
    <div className="relative">
      <input ref={ref} id={inputId} required={required} aria-invalid={!!error}
        className={clsx("input", error && "border-red-500 focus:border-red-500 focus:ring-red-500/20", suffix && "pr-12", className)} {...rest} />
      {suffix && <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs font-medium text-stone-500">{suffix}</span>}
    </div>
  );
  if (!label && !error && !hint) return input;
  return <Field label={label} hint={hint} error={error} htmlFor={inputId} required={required}>{input}</Field>;
});

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label?: ReactNode; hint?: ReactNode; error?: string;
  options: { value: string | number; label: string }[]; placeholder?: string;
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select({ label, hint, error, options, placeholder, className, id, required, ...rest }, ref) {
  const auto = useId();
  const selectId = id || auto;
  const el = (
    <select ref={ref} id={selectId} required={required} aria-invalid={!!error} className={clsx("input pr-8", className)} {...rest}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
  if (!label && !error && !hint) return el;
  return <Field label={label} hint={hint} error={error} htmlFor={selectId} required={required}>{el}</Field>;
});

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: ReactNode; hint?: ReactNode; error?: string };
export function Textarea({ label, hint, error, className, id, ...rest }: TextareaProps) {
  const auto = useId();
  const tid = id || auto;
  return (
    <Field label={label} hint={hint} error={error} htmlFor={tid}>
      <textarea id={tid} rows={3} className={clsx("input", className)} {...rest} />
    </Field>
  );
}

export function Checkbox({ label, hint, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; hint?: ReactNode }) {
  const id = useId();
  return (
    <div className={clsx("flex items-start gap-2.5", className)}>
      <input id={id} type="checkbox" className="mt-0.5 h-4 w-4 rounded border-stone-300 text-pine-700 focus:ring-pine-500" {...rest} />
      <label htmlFor={id} className="text-sm text-stone-700">
        {label}
        {hint && <span className="block text-xs text-stone-500">{hint}</span>}
      </label>
    </div>
  );
}

export function FormGrid({ children, cols = 2 }: { children: ReactNode; cols?: 1 | 2 | 3 | 4 }) {
  const map = { 1: "", 2: "sm:grid-cols-2", 3: "sm:grid-cols-2 lg:grid-cols-3", 4: "sm:grid-cols-2 lg:grid-cols-4" };
  return <div className={clsx("grid grid-cols-1 gap-4", map[cols])}>{children}</div>;
}

export function FormSection({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-stone-900">{title}</h3>
        {description && <p className="mt-0.5 text-xs text-stone-500">{description}</p>}
      </div>
      {children}
    </section>
  );
}
