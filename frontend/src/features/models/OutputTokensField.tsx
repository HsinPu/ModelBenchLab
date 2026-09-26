export const DEFAULT_OUTPUT_TOKENS = 32768;
export const MAX_OUTPUT_TOKENS = 131072;

export function validOutputTokens(value: string) {
  const number = Number(value);
  return value.trim() !== "" && Number.isInteger(number) && number >= 1 && number <= MAX_OUTPUT_TOKENS;
}

export default function OutputTokensField({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="mm-output-tokens-field">
      <span>輸出 Token 上限</span>
      <input
        type="number"
        min="1"
        max={MAX_OUTPUT_TOKENS}
        step="1"
        required
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
