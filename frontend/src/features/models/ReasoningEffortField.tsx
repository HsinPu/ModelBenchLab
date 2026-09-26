import type { ReasoningEffort } from "../../api";

export const reasoningLevels: ReasoningEffort[] = [
  "low",
  "medium",
  "high",
  "xhigh",
  "max",
  "ultra",
];

export default function ReasoningEffortField({
  value,
  onChange,
  disabled = false,
}: {
  value: ReasoningEffort | "";
  onChange: (value: ReasoningEffort | "") => void;
  disabled?: boolean;
}) {
  return (
    <label className="mm-reasoning-field">
      <span>思考程度</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) =>
          onChange(event.target.value as ReasoningEffort | "")
        }
      >
        <option value="">模型預設</option>
        {reasoningLevels.map((level) => (
          <option key={level} value={level}>
            {level}
          </option>
        ))}
      </select>
    </label>
  );
}
