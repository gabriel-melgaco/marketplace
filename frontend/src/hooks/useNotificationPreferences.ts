import { useCallback, useEffect, useState } from 'react';
import api from '@/api/axios';
import { NotificationPreference } from '@/types/notifications';

interface UseNotificationPreferencesReturn {
  preferences: NotificationPreference | null;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  updatePreferences: (partial: Partial<NotificationPreference>) => Promise<void>;
  togglePreference: (key: keyof NotificationPreference) => Promise<void>;
}

export function useNotificationPreferences(): UseNotificationPreferencesReturn {
  const [preferences, setPreferences] = useState<NotificationPreference | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPreferences = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const { data } = await api.get<NotificationPreference>('/notifications/preferences/');
      setPreferences(data);
    } catch (err) {
      setError('Não foi possível carregar as preferências.');
      console.error('[useNotificationPreferences] fetch error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPreferences();
  }, [fetchPreferences]);

  const updatePreferences = useCallback(
    async (partial: Partial<NotificationPreference>) => {
      if (!preferences) return;
      const previous = preferences;
      setPreferences((prev) => (prev ? { ...prev, ...partial } : prev));
      setIsSaving(true);
      setError(null);
      try {
        const { data } = await api.patch<NotificationPreference>('/notifications/preferences/', partial);
        setPreferences(data);
      } catch (err) {
        setPreferences(previous);
        setError('Não foi possível salvar as preferências.');
        console.error('[useNotificationPreferences] update error:', err);
        throw err;
      } finally {
        setIsSaving(false);
      }
    },
    [preferences]
  );

  const togglePreference = useCallback(
    async (key: keyof NotificationPreference) => {
      if (!preferences) return;
      const currentValue = preferences[key] as boolean;
      await updatePreferences({ [key]: !currentValue });
    },
    [preferences, updatePreferences]
  );

  return { preferences, isLoading, isSaving, error, updatePreferences, togglePreference };
}
