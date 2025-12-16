import { createApp } from 'vue';
import App from './App.vue';
import { Icon, icon } from 'leaflet';
import mitt from 'mitt';
import i18n from './i18n';

import 'leaflet/dist/leaflet.css';
import './assets/graphtactics.css';
import axios from 'axios';
import NProgress from 'nprogress';

// Create the event bus
export const emitter = mitt();

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
  error => {
    NProgress.done()
    var errorMsg
    if (error.status === 408 || error.code === 'ECONNABORTED') {
      errorMsg = i18n.global.t('app.error.timeout', { timeout: axiosConfig.timeout / 1000, url: error.config.url })
    }
    else
      errorMsg = i18n.global.t('app.error.unknown', { url: error.config.url })
    emitter.emit('done', errorMsg)
    return Promise.reject(error);
  })

// Leaflet icon fix
delete Icon.Default.prototype._getIconUrl;

Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

export const myIcons = {
  'carAssignable': icon({
    iconUrl: require("@/assets/car.svg"),
    iconSize: [25, 25],
    iconAnchor: [12, 10]
  }),
  'carAssigned': icon({
    iconUrl: require("@/assets/car.svg"),
    iconSize: [25, 25],
    iconAnchor: [12, 10]
  }),
  'carUnassigned': icon({
    iconUrl: require("@/assets/car_grey.svg"),
    iconSize: [25, 25],
    iconAnchor: [12, 10]
  }),
  'origin': icon({
    iconUrl: require("@/assets/origin.svg"),
    iconSize: [40, 40],
    iconAnchor: [12, 10]
  }),
  'barrage': icon({
    iconUrl: require("@/assets/barrage.png"),
    iconSize: [30, 30],
    iconAnchor: [13, 27],
    popupAnchor: [1, -24]
  }),
  'endpoint': icon({
    iconUrl: require("@/assets/pin.png"),
    iconAnchor: [20, 40],
    iconSize: [40, 40],
  }),
};

const app = createApp(App);

app.use(i18n);

// Make axios available globally
app.config.globalProperties.$axios = $axios;

app.mount('#app');