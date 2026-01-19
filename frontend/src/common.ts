import mitt from 'mitt';
import { icon } from 'leaflet';

// Create the event bus
type Events = {
    loading: void;
    done: string | undefined;
};
export const emitter = mitt<Events>();

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
    'en-controlled': icon({
        iconUrl: require("@/assets/pin-green.png"),
        iconAnchor: [15, 30],
        iconSize: [30, 30],
    }),
    'en-uncontrolled': icon({
        iconUrl: require("@/assets/pin-red.png"),
        iconAnchor: [15, 30],
        iconSize: [30, 30],
    }),
    'en-irrelevant': icon({
        iconUrl: require("@/assets/pin-grey.png"),
        iconAnchor: [15, 30],
        iconSize: [30, 30],
    }),
};
