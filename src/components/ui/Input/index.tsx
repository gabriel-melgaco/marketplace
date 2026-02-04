import type { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

export function Input(props: InputProps) {
  return (
    <div>
      <input
        {...props}
        className={`h-8 md:10 bg-amber-50 px-3 rounded-lg text-base focus: outline-none placeholder:text-gray-950 ${props.className ?? ""}`}
      />
    </div>
  );
}
