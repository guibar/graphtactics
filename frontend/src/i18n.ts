import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import fr from './locales/fr.json'

function getBrowserLocale(): string | undefined {
  const navigatorLocale = navigator.languages !== undefined
    ? navigator.languages[0]
    : navigator.language

  if (!navigatorLocale) {
    return undefined
  }

  const trimmedLocale = navigatorLocale.trim().split(/-|_/)[0]
  return trimmedLocale
}

function getStartingLocale(): string {
  const persistedLocale = localStorage.getItem('user-locale')
  if (persistedLocale) {
    return persistedLocale
  }
  const browserLocale = getBrowserLocale()
  if (browserLocale === 'fr') {
    return 'fr'
  }
  return 'en'
}

const i18n = createI18n({
  legacy: true, // We want to use Options API
  locale: getStartingLocale(),
  fallbackLocale: 'en',
  messages: {
    en,
    fr
  }
})

export default i18n
