import { createApp } from 'vue';
import App from './App.vue';
import { Icon } from 'leaflet';
import i18n from './i18n';
import { emitter } from './common';

import 'leaflet/dist/leaflet.css';
import './assets/graphtactics.css';
import axios, { AxiosError } from 'axios';
import NProgress from 'nprogress';

// Configure Axios
const axiosConfig = {
  baseURL: '/api/',  // Use /api/ prefix for proxy to intercept
  timeout: 80000,
};

const $axios = axios.create(axiosConfig);

$axios.interceptors.request.use(config => {
  NProgress.start()
  emitter.emit('loading')
  return config
})

$axios.interceptors.response.use(
  response => {
    emitter.emit('done')
    NProgress.done()
    return response
  },
  (error: AxiosError) => {
    NProgress.done()
    let errorMsg: string;
    if (error.code === 'ECONNABORTED' || error.response?.status === 408) {
      errorMsg = i18n.global.t('app.error.timeout', { timeout: axiosConfig.timeout / 1000, url: error.config?.url })
    }
    else
      errorMsg = i18n.global.t('app.error.unknown', { url: error.config?.url })
    emitter.emit('done', errorMsg)
    return Promise.reject(error);
  })

// Leaflet icon fix
delete (Icon.Default.prototype as any)._getIconUrl;

Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

const app = createApp(App);

app.use(i18n);

// Make axios available globally
app.config.globalProperties.$axios = $axios;

app.mount('#app');