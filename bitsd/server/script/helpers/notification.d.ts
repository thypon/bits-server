interface Notification extends EventTarget {
  onclick: (ev: MouseEvent) => any;
  onshow: () => any;
  onerror: ErrorEventHandler;
  onclose: (ev: CloseEvent) => any;

  dir: NotificationDirection;
  lang: string;
  body: string;
  tag: string;
  icon: string;

  close(): void;
}

interface NotificationPermissionCallback {
    (permission: NotificationPermission): void;
}

interface NotificationPermission extends string { /* default, denied, granted */}

interface NotificationDirection extends string { /* auto, ltr, rtl */ }

interface NotificationOptions {
  dir?: NotificationDirection;
  lang?: string;
  body?: string;
  tag?: string;
  icon?: string;
}

declare var Notification: {
    new (title: string, options?: NotificationOptions);

    prototype: Notification;

    permission: NotificationPermission;
    requestPermission(callback?: NotificationPermissionCallback);
}