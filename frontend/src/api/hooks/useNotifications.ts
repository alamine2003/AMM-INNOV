import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Notification, Paginated } from '@/api/types';

export function useNotifications(unreadOnly = false, enabled = true) {
  return useQuery({
    queryKey: queryKeys.notifications.list(unreadOnly),
    queryFn: async () => {
      // Seul le canal in-app est affiché dans la cloche : les notifications e-mail sont des
      // doublons du même événement (une ligne par canal côté serveur).
      const res = await api.get<Paginated<Notification> | Notification[]>('/notifications', {
        params: unreadOnly ? { unread: 1, channel: 'IN_APP' } : { page_size: 50, channel: 'IN_APP' },
      });
      return Array.isArray(res.data) ? res.data : res.data.results;
    },
    enabled,
  });
}

export function useUnreadCount(enabled = true, refetchInterval: number | false = false) {
  return useQuery({
    queryKey: queryKeys.notifications.unreadCount(),
    queryFn: async () => (await api.get<{ unread: number }>('/notifications/unread-count')).data.unread,
    enabled,
    refetchInterval,
  });
}

export function useNotificationActions() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: queryKeys.notifications.all });
  const markRead = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/notifications/${id}/read`);
    },
    onSuccess: invalidate,
  });
  const markAllRead = useMutation({
    mutationFn: async () => {
      await api.post('/notifications/read-all');
    },
    onSuccess: invalidate,
  });
  return { markRead, markAllRead };
}
