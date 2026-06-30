import * as React from "react";
import { Copy, Edit3, Image, Monitor, Moon, Palette, Plus, Save, Sun, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Field, NumberField, SettingsActions, SettingsSection, clamp } from "@/pages/settings/shared";
import {
  allThemePresets,
  type AppearanceSettings,
  type ColorScheme,
  type ThemePreset,
  type ThemePresetIcon
} from "@/lib/theme";

export type AppearanceSettingsTabProps = {
  activePreset: ThemePreset;
  customPresets: ThemePreset[];
  settings: AppearanceSettings;
  onCreatePreset: (basePresetId: string, name?: string) => void;
  onDeletePreset: (presetId: string) => void;
  onSetActivePreset: (presetId: string) => void;
  onSetFollowSystem: (followSystem: boolean) => void;
  onSetSystemPreset: (scheme: ColorScheme, presetId: string) => void;
  onUpdatePreset: (preset: ThemePreset) => void;
};

export function AppearanceSettingsTab({
  activePreset,
  customPresets,
  settings,
  onCreatePreset,
  onDeletePreset,
  onSetActivePreset,
  onSetFollowSystem,
  onSetSystemPreset,
  onUpdatePreset
}: AppearanceSettingsTabProps): JSX.Element {
  const presets = allThemePresets(customPresets);
  const lightPresets = presets.filter((preset) => preset.scheme === "light");
  const darkPresets = presets.filter((preset) => preset.scheme === "dark");
  const [editingPresetId, setEditingPresetId] = React.useState<string | null>(null);
  const editingPreset = customPresets.find((preset) => preset.id === editingPresetId) ?? null;

  return (
    <div className="mt-5 divide-y">
      <SettingsSection title="Mode" description="Choose whether preset selection follows the operating system.">
        <div className="space-y-3">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-4 rounded-md border bg-background p-3 text-left transition-colors hover:bg-muted"
            aria-pressed={settings.followSystem}
            onClick={() => onSetFollowSystem(!settings.followSystem)}
          >
            <span className="flex min-w-0 items-start gap-3">
              <Monitor className="mt-0.5 h-4 w-4 text-primary" aria-hidden="true" />
              <span className="min-w-0">
                <span className="block text-sm font-medium">Follow system appearance</span>
                <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                  Switch between the selected light and dark presets with the operating system.
                </span>
              </span>
            </span>
            <span
              className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors ${
                settings.followSystem ? "border-primary bg-primary" : "bg-muted"
              }`}
              aria-hidden="true"
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-background shadow-sm transition-transform ${
                  settings.followSystem ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </span>
          </button>

          {settings.followSystem ? (
            <div className="rounded-md border bg-muted/25 p-3">
              <span className="mt-1 block text-xs leading-5 text-muted-foreground">Current mapping</span>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field label="When system is light">
                  <Select value={settings.systemLightPresetId} onChange={(event) => onSetSystemPreset("light", event.target.value)}>
                    {lightPresets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="When system is dark">
                  <Select value={settings.systemDarkPresetId} onChange={(event) => onSetSystemPreset("dark", event.target.value)}>
                    {darkPresets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            </div>
          ) : (
            <Field label="Active preset">
              <Select value={settings.activePresetId} onChange={(event) => onSetActivePreset(event.target.value)}>
                {presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>
      </SettingsSection>

      <SettingsSection title="Presets" description="Apply, duplicate, edit, or delete local appearance presets.">
        <div className="space-y-3">
          <div className="grid gap-2 sm:grid-cols-2">
            {presets.map((preset) => (
              <ThemePresetCard
                key={preset.id}
                active={activePreset.id === preset.id}
                preset={preset}
                onApply={() => onSetActivePreset(preset.id)}
                onCreate={() => onCreatePreset(preset.id)}
                onDelete={() => onDeletePreset(preset.id)}
                onEdit={() => setEditingPresetId(preset.id)}
              />
            ))}
          </div>
          <Button type="button" variant="outline" onClick={() => onCreatePreset(activePreset.id, `${activePreset.name} Copy`)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            New From Current
          </Button>
        </div>
      </SettingsSection>

      {editingPreset ? (
        <SettingsSection title="Editor" description="Edit the selected user preset. Built-in presets can be duplicated first.">
          <ThemePresetEditor preset={editingPreset} onCancel={() => setEditingPresetId(null)} onSave={onUpdatePreset} />
        </SettingsSection>
      ) : null}
    </div>
  );
}

function ThemePresetCard({
  active,
  preset,
  onApply,
  onCreate,
  onDelete,
  onEdit
}: {
  active: boolean;
  preset: ThemePreset;
  onApply: () => void;
  onCreate: () => void;
  onDelete: () => void;
  onEdit: () => void;
}): JSX.Element {
  const Icon = themePresetIcon(preset.icon);
  return (
    <div className={`rounded-md border p-3 ${active ? "border-primary bg-primary/10" : "bg-background"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="flex items-center gap-2 text-sm font-semibold">
            <Icon className="h-4 w-4" aria-hidden="true" />
            <span className="truncate">{preset.name}</span>
          </span>
          <span className="mt-1 block text-xs capitalize text-muted-foreground">
            {preset.scheme} · {preset.source === "system" ? "Built-in" : "User"}
          </span>
        </div>
        {active ? <span className="text-xs font-medium text-primary">Active</span> : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onApply}>
          Apply
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCreate}>
          <Copy className="h-4 w-4" aria-hidden="true" />
          Duplicate
        </Button>
        {!preset.readonly ? (
          <>
            <Button type="button" variant="outline" size="sm" onClick={onEdit}>
              <Edit3 className="h-4 w-4" aria-hidden="true" />
              Edit
            </Button>
            <Button type="button" variant="outline" size="sm" className="text-destructive" onClick={onDelete}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Delete
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}

function ThemePresetEditor({
  preset,
  onCancel,
  onSave
}: {
  preset: ThemePreset;
  onCancel: () => void;
  onSave: (preset: ThemePreset) => void;
}): JSX.Element {
  const [draft, setDraft] = React.useState<ThemePreset>(preset);

  React.useEffect(() => {
    setDraft(preset);
  }, [preset]);

  return (
    <div className="space-y-4">
      <Field label="Name">
        <Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
      </Field>
      <Field label="Scheme">
        <Select value={draft.scheme} onChange={(event) => setDraft({ ...draft, scheme: event.target.value as ColorScheme })}>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </Select>
      </Field>
      <Field label="Icon">
        <Select value={draft.icon} onChange={(event) => setDraft({ ...draft, icon: event.target.value as ThemePresetIcon })}>
          <option value="sun">Sun</option>
          <option value="moon">Moon</option>
          <option value="palette">Palette</option>
          <option value="image">Image</option>
        </Select>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Primary token">
          <Input
            value={draft.tokens.primary}
            onChange={(event) => setDraft({ ...draft, tokens: { ...draft.tokens, primary: event.target.value } })}
            placeholder="207 80% 40%"
          />
        </Field>
        <Field label="Accent token">
          <Input
            value={draft.tokens.accent}
            onChange={(event) => setDraft({ ...draft, tokens: { ...draft.tokens, accent: event.target.value } })}
            placeholder="46 88% 88%"
          />
        </Field>
      </div>
      <Field label="Background URL">
        <Input
          value={draft.background.imageUrl}
          onChange={(event) =>
            setDraft({
              ...draft,
              background: { ...draft.background, type: event.target.value.trim() ? "image" : "none", imageUrl: event.target.value }
            })
          }
          placeholder="https://..."
        />
      </Field>
      <div className="grid gap-3 sm:grid-cols-3">
        <NumberField
          label="Opacity"
          value={draft.background.opacity}
          min={0}
          max={1}
          step={0.05}
          onChange={(value) => setDraft({ ...draft, background: { ...draft.background, opacity: clamp(value, 0, 1) } })}
        />
        <NumberField
          label="Dim"
          value={draft.background.dim}
          min={0}
          max={1}
          step={0.05}
          onChange={(value) => setDraft({ ...draft, background: { ...draft.background, dim: clamp(value, 0, 1) } })}
        />
        <NumberField
          label="Blur"
          value={draft.background.blur}
          min={0}
          step={1}
          onChange={(value) => setDraft({ ...draft, background: { ...draft.background, blur: Math.max(0, value) } })}
        />
      </div>
      <SettingsActions>
        <Button
          type="button"
          onClick={() =>
            onSave({
              ...draft,
              name: draft.name.trim() || preset.name,
              background: { ...draft.background, type: draft.background.imageUrl.trim() ? "image" : "none" }
            })
          }
        >
          <Save className="h-4 w-4" aria-hidden="true" />
          Save Preset
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </SettingsActions>
    </div>
  );
}

function themePresetIcon(icon: ThemePresetIcon) {
  if (icon === "sun") {
    return Sun;
  }
  if (icon === "moon") {
    return Moon;
  }
  if (icon === "image") {
    return Image;
  }
  return Palette;
}
