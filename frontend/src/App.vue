<template>
  <div id="app">
    <help-modal v-if="showHelp" @close="showHelp = false" />
    <div id="controls">
      <div id="logoname">
        <div id="logo">
              <img v-show="!loading" alt="GraphTactics logo" src="@/assets/graphtactics.png">
              <div v-if="loading" class="spinner"></div>
        </div>
        <div id="title">GraphTactics</div>
        <div id="help"><img src="@/assets/help.svg" width="30px" v-on:click="showHelp = true"/></div>
        <div id="lang-switch" @click="switchLanguage">{{ currentLocale }}</div>
      </div>
      <div id="descriptif">{{ $t('app.title') }}</div>

      <div id="inputs" class="grid-container">
        <div>
          {{ $t('app.department') }}
        </div>
        <div>
          <select v-model="zone" v-on:change="onZoneChange()" class="input-select">
            <option v-for="network in availableNetworks" :key="network" :value="network">
              {{ network }}
            </option>
          </select>
        </div>

        <div class="t-ecoule">{{ $t('app.elapsedTime') }}</div>
        <div>
          <input type="number" :disabled="loading || results" v-model.number="mins" class="input-number"/> {{ $t('app.mins') }}
        </div>
        <div>
          <input type="number" :disabled="loading || results" v-model.number="secs" class="input-number"/> {{ $t('app.secs') }}
        </div>

        <div>
          {{ $t('app.nbVehicles') }} 
        </div>
        <div>
          <input type="number" :disabled="loading || results" v-model.number="nb_random_vehicles" class="input-number"/>
          = x
        </div>
        <div class="b-veh">
          <button class="button" :disabled="loading || results" v-on:click="getRandomVehicles">
            {{ $t('app.getVehicles') }}
          </button>
        </div>
        <div class="b-veh">
          <button class="button"  :disabled="loading || results" v-on:click="generatePlan">{{ $t('app.generate') }}</button>
        </div>
      </div>
      <div id="clear">
        <button class="button-clear-dispo" :disabled="loading" v-on:click="clearOutput">{{ $t('app.clearOutput') }}</button>
        <button class="button-clear-all" :disabled="loading" v-on:click="clearAll">{{ $t('app.clearAll') }}</button>
      </div>
      <stats v-if="stats_model" :stats="stats_model"/>
      <div id="outputs" v-html="outputsContent"></div>
    </div>

    <l-map ref="map"
      v-model:zoom="zoom"
      v-model:center="center"
      :bounds="bounds"
      @click="addVehicle"
      id="map"
    >
      <l-control-layers ref="layerControl" position="bottomleft"></l-control-layers>

      <l-tile-layer :disabled="true" :url="osmUrl">
      </l-tile-layer>
P
      <l-layer-group name="Limites" layer-type="overlay" ref="boundaries_lg">
        <l-geo-json v-if="boundariesGJ" :geojson="boundariesGJ" :options-style="boundaryStyle"></l-geo-json>
      </l-layer-group>

      <l-marker v-if="originCoords" v-model:lat-lng="originCoords" :draggable="!results && !loading" :clickable=true 
          :icon="originIcon" ref="orig_marker"></l-marker>

      <l-layer-group name="Points de Fuite" layer-type="overlay" ref="escape_points_lg">
        <l-geo-json v-if="escapePointsGJ" :geojson="escapePointsGJ" :options="escapeOptions"></l-geo-json>
      </l-layer-group>

      <l-layer-group name="Vehicules" layer-type="overlay">
        <l-marker
            v-for="v in vehicles"
            :key="v.id"
            :visible="v.visible"
            :draggable="!results && !loading"
            v-model:lat-lng="v.position"
            :icon="v.status == 0?carAssignableIcon:v.status==4?carAssignedIcon:carUnassignedIcon"
            @click="removeVehicle(v)"
        >
          <l-tooltip :content="v.tooltip" />
        </l-marker>
      </l-layer-group>

      <l-layer-group name="Trajets Passés" layer-type="overlay" ref="to_njois_lg">
        <l-geo-json v-if="toNjoisGJ" :geojson="toNjoisGJ" :options-style="toNjoisStyle"></l-geo-json>
      </l-layer-group>

      <l-layer-group name="Isochrone" layer-type="overlay" ref="isochrone_lg">
        <l-geo-json v-if="isochroneGJ" :geojson="isochroneGJ" :options-style="isochroneStyle"></l-geo-json>
      </l-layer-group>

      <l-layer-group name="Trajets Futurs" layer-type="overlay" ref="from_njois_lg">
        <l-geo-json v-if="fromNjoisGJ" :geojson="fromNjoisGJ" :options-style="fromNjoisStyle"></l-geo-json>
      </l-layer-group>

      <l-layer-group name="Affectations" layer-type="overlay" ref="affectations_lg">
        <l-geo-json v-if="affectationsGJ" :geojson="affectationsGJ" :options="affectationsOptions"></l-geo-json>
      </l-layer-group>

      <l-layer-group name="Destinations" layer-type="overlay" ref="destinations_lg">
        <l-geo-json v-if="destinationsGJ" :geojson="destinationsGJ" :options="destinationsOptions"></l-geo-json>
      </l-layer-group>

    </l-map>
  </div>
</template>

<script>
import L from "leaflet";
import { myIcons, emitter } from "@/main";
import { LMap, LTileLayer, LMarker, LGeoJson, LControlLayers, LLayerGroup, LTooltip} from '@vue-leaflet/vue-leaflet';
import 'leaflet-arrowheads'
import HelpModal from './Help.vue'
import Stats from './Stats.vue'

export default {
  name: "App",
  components: {
    'l-map': LMap,
    'l-tile-layer': LTileLayer,
    'l-marker': LMarker,
    'l-geo-json': LGeoJson,
    'l-control-layers': LControlLayers,
    'l-layer-group': LLayerGroup,
    'l-tooltip': LTooltip,
    'help-modal': HelpModal,
    'stats': Stats
  },  
  data: function () {
    return {
      map: null,
      zoom: 13,
      center: [0, 0],
      bounds: null,
      osmUrl: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      zone: '60',
      availableNetworks: [],
      // Layers
      boundariesGJ: null,
      escapePointsGJ: null,
      affectationsGJ: null,
      destinationsGJ: null,
      isochroneGJ: null,
      toNjoisGJ: null,
      fromNjoisGJ: null,
      originCoords: null,

      mins: 5,
      secs: 0,
      nb_random_vehicles: 10,
      vid: 1,
      vehicles: [],
      carAssignableIcon: myIcons["carAssignable"],
      carAssignedIcon: myIcons["carAssigned"],
      carUnassignedIcon: myIcons["carUnassigned"],
      originIcon: myIcons["origin"],
      loading: false,
      results: false,
      stats_model:null,
      outputsContent: null,
      showHelp: false,

      isochroneStyle: {
        weight: 2,
        color: "#fe7000",
        fillColor: "#00fe7e",
        fillOpacity: 0.2,
      },
      fromNjoisStyle: function(feature) {
        return {
          weight: 4,
          color: feature.properties.watched?"#fe3400":"#00ff00",
          opacity: 0.9,
          zIndex: -10
        }
      },
      toNjoisStyle: {
        weight: 4,
        color: "#fcff00",
        opacity: 1,
      },
      boundaryStyle: {
        weight: 2,
        color: "#000000",
        opacity: 1,
        fillOpacity: 0,
      }
    };
  },

  computed: {
    escapeOptions() {
      return {
        pointToLayer: function (feature, latlng) {
          return L.marker(latlng, {icon: myIcons["endpoint"]});
        }
      }
    },
    destinationsOptions() {
      return {
        onEachFeature: this.onEachDestinationFeatureFunction
      };
    },
    onEachDestinationFeatureFunction() {
      return (feature, layer) => {
        layer.setIcon(myIcons["barrage"])
        layer.bindTooltip(this.$t('app.tooltips.destination', { id: feature.properties.vid }),
          { permanent: false, 
            sticky: true }
        );
      };
    },

    affectationsOptions() {
      return {
        weight: 3,
        dashArray: "2 5",
        color: "#0000ff",
        opacity: 1,
        arrowheads: {
            weight: 1,
            dashArray: "5 0",
            yawn: 45,
            fill: true,
            color: 'black',
            fillColor: '#00fff6',
            size: "10px",
            frequency: "30px"
        }, 
        onEachFeature: this.onEachAffectationFeatureFunction,
      };
    },
    onEachAffectationFeatureFunction() {
      return (feature, layer) => {
        layer.on('mouseover', function (e) {
          e.target.setStyle({
              color: "#ff00ff",
              weight: 5
          });
        });
        layer.on('mouseout', function (e) {
          e.target.setStyle({
              color: "#0000ff",
              weight: 3
          });
        });
        layer.bindTooltip(this.$t('app.tooltips.affectation', {
            vid: feature.properties.vid,
            origin: feature.properties.origin,
            destination: feature.properties.destination,
            travel_time: feature.properties.travel_time,
            time_margin: feature.properties.time_margin,
            score: feature.properties.score
          }),
          { permanent: false, sticky: true }
        );
      };
    },
    currentLocale() {
      return this.$i18n.locale.toUpperCase();
    }
  },

  mounted() {
    this.fetchNetworks()
  },
  created() {
    emitter.on('loading', this.setLoading);
    emitter.on('done',  this.setDone);
  },
  beforeUnmount() {
    emitter.off('loading', this.setLoading);
    emitter.off('done',  this.setDone);
  },

  methods: {
    fetchNetworks: function() {
      this.$axios
        .get('networks').then((response) => {
          if (response.status === 200) {
            this.availableNetworks = response.data.available;
            this.zone = response.data.current;
            this.onZoneChange(true);
          }
        }).catch((error) => {
          console.error('Error fetching networks:', error);
          // Fallback to default zone if API fails
          this.availableNetworks = ['60'];
          this.onZoneChange(true);
        });
    },

    onZoneChange(isInit = false) {
        if (!isInit) {
            this.boundariesGJ = null;
            this.clearAll()
        }
        
        const request = isInit 
            ? this.$axios.get('init') 
            : this.$axios.post(`networks/${this.zone}`);

        request
          .then((response) => {
            if (response.status === 200) {
              const data = response.data;
              this.boundariesGJ = data["boundaries"];
              
              // Calculate bounds for the map view
              const tempGeo = L.geoJSON(data["boundaries"]);
              this.bounds = tempGeo.getBounds();

              this.escapePointsGJ = data["escape_points"];
              this.originCoords = data["origin_coords"];
            }
          })
          .catch((error) => {
            console.error('Error loading zone:', error);
          });
    },
    generatePlan: function () {
      if (this.vehicles.length == 0) {
        alert(this.$t('app.error.noVehicles'));
        return
      }
      this.$axios
        .post(`generate`, {
          vehicles: this.vehicles.map(v => ({
            id: v.id,
            lat_lng: { lat: v.position.lat, lng: v.position.lng }
          })),
          origin_coords: { lat: this.originCoords.lat, lng: this.originCoords.lng },
          time_delta: this.mins*60 + this.secs
        })
        .then((response) => {
          if (response.status === 200) {
            this.results = true
            this.originCoords = L.latLng(response.data["origin"])
            // reset the vehicles with the ones received from the response
            this.vehicles = [];
            this.addToVehicles(response.data["vehicles"]);
            const travelData = response.data["travel_data"];
            this.toNjoisGJ = travelData["paths_to_njois"];
            this.isochroneGJ = travelData["isochrone"];
            this.fromNjoisGJ = travelData["paths_from_njois"];
            this.affectationsGJ = response.data["affectations"];
            this.destinationsGJ = response.data["destinations"];
            this.stats_model = response.data["stats"]
            
            // Visibility is handled by v-if="...GJ" in the template. 
            // Since we just set the data, they will appear.
          }
        });
    },

    setLoading() {
      this.loading = true;
    },
    setDone(eventMessage) {
      if (eventMessage) {
        this.outputsContent = eventMessage
      }
      this.loading = false;
    },

    addVehicle: function (e) {
      if (!this.results && !this.loading) {
        this.vehicles.push({
          id: this.vid,
          position: e.latlng,
          visible: true,
          tooltip: this.$t('app.tooltips.vid', { id: this.vid }),
          status: 0
        })
        this.vid++;
      }
    },

    removeVehicle: function(v) {
      const index = this.vehicles.indexOf(v);
      if (!this.results && !this.loading && index > -1) {
        this.vehicles.splice(index, 1);
      }
    },

    addToVehicles: function(vehicles_json) {
      for(var i = 0; i < vehicles_json.length; i++) {
        this.vehicles.push(
          { id: vehicles_json[i].id,
            position: vehicles_json[i].position,
            visible: true,
            tooltip: this.$t('app.tooltips.vid', { id: vehicles_json[i].id }),
            status: vehicles_json[i].status
          })
      }
    },

    switchLanguage() {
      const newLocale = this.$i18n.locale === 'fr' ? 'en' : 'fr';
      this.$i18n.locale = newLocale;
      localStorage.setItem('user-locale', newLocale);
    },

    clearOutput: function () {
      this.affectationsGJ = null
      this.toNjoisGJ = null
      this.fromNjoisGJ = null
      this.isochroneGJ = null
      this.destinationsGJ = null
      this.results = false
      this.stats_model = null
      this.outputsContent = ""
      
      this.vehicles.forEach(function (v) {
        v.status = 0;
      });
    },

    clearAll: function () {
      this.clearOutput()
      this.vehicles = []
      this.vid = 1;
    },

    getRandomVehicles: function () {
      let params = {nb_vh: this.nb_random_vehicles}
      this.$axios
        .get(`random_vehicles`, {params: params})
        .then((response) => {
          if (response.status === 200) {
            this.addToVehicles(response.data)
          }
        });
    },
  },
};
</script>

<style>
.spinner {
  border: 4px solid rgba(0, 0, 0, 0.1);
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border-left-color: #ff0000;
  animation: spin 1s linear infinite;
  display: inline-block;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>
