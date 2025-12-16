<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h1>{{ $t('help.title') }}</h1>
        <button class="close-button" @click="$emit('close')">&times;</button>
      </div>
      <div class="modal-body">
        {{ $t('help.intro') }}
          <h2>{{ $t('help.dataTitle') }}</h2>
            <ol>
              <li>{{ $t('help.point1') }}
                <ul>
                  <li>{{ $t('help.point1_sub1') }}</li>
                  <li>{{ $t('help.point1_sub2') }}</li>
                </ul>
              </li>
              <li>{{ $t('help.point2_pre') }} <img src="@/assets/origin.svg" width=25px> 
              {{ $t('help.point2_post') }}</li>
              <li>{{ $t('help.point3') }}
              </li>
              <li>{{ $t('help.point4') }}
                <ul>
                  <li>{{ $t('help.point4_sub1') }}</li>
                  <li>{{ $t('help.point4_sub2_pre') }} <span>{{ $t('help.point4_sub2_btn') }}</span> 
                  {{ $t('help.point4_sub2_post') }} </li>
                </ul>
                {{ $t('help.point4_end') }}
              </li>
            </ol> 
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
  name: "HelpModal",
  emits: ['close']
});
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10000;
}

.modal-content {
  background-color: white;
  padding: 20px;
  border-radius: 8px;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.close-button {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
}
</style>