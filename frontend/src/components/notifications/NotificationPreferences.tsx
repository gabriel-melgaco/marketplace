import React from 'react';
import { useNotificationPreferences } from '@/hooks/useNotificationPreferences';
import { NotificationPreference, NotificationType } from '@/types/notifications';
import { getNotificationMeta, NOTIFICATION_TYPE_GROUPS } from '@/utils/notificationUtils';

export function NotificationPreferences() {
  const { preferences, isLoading, isSaving, error, togglePreference } = useNotificationPreferences();

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-16">
        <div className="h-6 w-6 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!preferences) {
    return (
      <div className="text-center py-8 text-gray-500">
        {error ?? 'Não foi possível carregar as preferências.'}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm border border-red-200">{error}</div>
      )}

      {isSaving && (
        <div className="p-3 rounded-lg bg-blue-50 text-blue-700 text-sm border border-blue-200 flex items-center gap-2">
          <div className="h-4 w-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
          Salvando preferências...
        </div>
      )}

      {NOTIFICATION_TYPE_GROUPS.map((group) => (
        <div key={group.groupLabel} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h3 className="text-sm font-semibold text-gray-700">{group.groupLabel}</h3>
          </div>
          <div className="divide-y divide-gray-100">
            {group.types.map((notifType) => (
              <PreferenceRow
                key={notifType}
                notifType={notifType}
                preferences={preferences}
                onToggle={togglePreference}
                disabled={isSaving}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

interface PreferenceRowProps {
  notifType: NotificationType;
  preferences: NotificationPreference;
  onToggle: (key: keyof NotificationPreference) => Promise<void>;
  disabled: boolean;
}

function PreferenceRow({ notifType, preferences, onToggle, disabled }: PreferenceRowProps) {
  const meta = getNotificationMeta(notifType);
  const wsKey = `${notifType}_ws` as keyof NotificationPreference;
  const emailKey = `${notifType}_email` as keyof NotificationPreference;
  const wsEnabled = preferences[wsKey] as boolean;
  const emailEnabled = preferences[emailKey] as boolean;

  return (
    <div className="flex items-center justify-between px-4 py-3">
      <span className={`text-sm font-medium ${meta.colorClass}`}>{meta.label}</span>
      <div className="flex items-center gap-6">
        <label className="flex items-center gap-2 cursor-pointer">
          <Toggle
            checked={wsEnabled}
            onChange={() => onToggle(wsKey)}
            disabled={disabled}
            ariaLabel={`Receber "${meta.label}" em tempo real`}
          />
          <span className="text-xs text-gray-500">Tempo real</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <Toggle
            checked={emailEnabled}
            onChange={() => onToggle(emailKey)}
            disabled={disabled}
            ariaLabel={`Receber "${meta.label}" por email`}
          />
          <span className="text-xs text-gray-500">Email</span>
        </label>
      </div>
    </div>
  );
}

interface ToggleProps {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  ariaLabel: string;
}

function Toggle({ checked, onChange, disabled, ariaLabel }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed ${
        checked ? 'bg-blue-600' : 'bg-gray-200'
      }`}
    >
      <span
        aria-hidden="true"
        className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-5' : 'translate-x-1'
        }`}
      />
    </button>
  );
}
