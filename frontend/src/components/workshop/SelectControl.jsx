import { Children, isValidElement } from "react";
import { Select } from "@base-ui/react/select";
import { Check, ChevronDown } from "lucide-react";

// Preserve the existing value/onChange contract while sharing one accessible popup.
export function SelectControl({
  children,
  value,
  defaultValue,
  onChange,
  disabled,
  required,
  name,
  className = "",
  ...props
}) {
  const items = Children.toArray(children)
    .filter(isValidElement)
    .map((child) => ({
      value: String(
        child.props.value ?? Children.toArray(child.props.children).join(""),
      ),
      label: child.props.children,
      disabled: child.props.disabled,
    }));
  return (
    <Select.Root
      value={value === undefined ? undefined : String(value ?? "")}
      defaultValue={
        defaultValue === undefined ? undefined : String(defaultValue)
      }
      onValueChange={(next) => onChange?.({ target: { value: next ?? "" } })}
      items={items}
      disabled={disabled}
      required={required}
      name={name}
    >
      <Select.Trigger
        data-value={String(value ?? defaultValue ?? "")}
        {...props}
        className={`w-select ${className}`}
      >
        <Select.Value />
        <Select.Icon className="w-select-chevron">
          <ChevronDown size={16} aria-hidden="true" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner
          className="w-select-positioner"
          sideOffset={6}
          alignItemWithTrigger={false}
        >
          <Select.Popup className="w-select-popup">
            <Select.List className="w-select-list">
              {items.map((item) => (
                <Select.Item
                  className="w-select-option"
                  key={item.value}
                  value={item.value}
                  disabled={item.disabled}
                  data-value={item.value}
                >
                  <Select.ItemText>{item.label}</Select.ItemText>
                  <Select.ItemIndicator className="w-select-check">
                    <Check size={15} aria-hidden="true" />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}
