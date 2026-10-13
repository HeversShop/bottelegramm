type TelegramUser = {
  id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
};

type TelegramWebApp = {
  initData: string;
  initDataUnsafe: { user?: TelegramUser };
  ready: () => void;
  expand: () => void;
  showAlert?: (message: string) => void;
  close?: () => void;
};

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

export const telegramWebApp = window.Telegram?.WebApp;

export function initializeTelegram(): string {
  telegramWebApp?.ready();
  telegramWebApp?.expand();
  return telegramWebApp?.initData ?? "";
}

export function notify(message: string): void {
  if (telegramWebApp?.showAlert) telegramWebApp.showAlert(message);
  else window.alert(message);
}

