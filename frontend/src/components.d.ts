

import { AxiosInstance } from 'axios';

declare module '@vue/runtime-core' {
    interface ComponentCustomProperties {
        $axios: AxiosInstance;
        $t: (key: string, values?: any) => string;
        $i18n: { locale: string };
    }
}
