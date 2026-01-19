<template>
<div id=stats>
    <h4>{{ $t('stats.title') }}</h4>
    <table class='main'>
      <tbody>
        <tr><td>{{ $t('stats.nbEscapeNodes') }}</td>   <td class='value'>{{stats['nb_escape_nodes']}}</td></tr>
        <tr><td>{{ $t('stats.nbIsochronePoints') }}</td> <td class='value'>{{stats['nb_njois']}}</td></tr>
        <tr><td>{{ $t('stats.nbCandidateNodes') }}</td>  <td class='value'>{{stats['nb_candidate_nodes']}}</td></tr>
        <tr><td>{{ $t('stats.maxScore') }}</td>     <td class='value'>{{stats['max_possible_score']}}</td></tr>
        <tr><td>{{ $t('stats.score') }}</td>      <td class='value'>{{stats['score']}}</td></tr>
        <tr><td>{{ $t('stats.tightness') }}</td>        <td class='value'> 
                                        {{(stats['score']*100/stats['max_possible_score']).toFixed(0)}}%</td></tr>
        <tr><td>{{ $t('stats.nbVehicles') }}</td><td class='value'>{{stats['nb_vehicles']}}</td></tr>
        <tr><td>{{ $t('stats.nbAssignments') }}</td><td class='value'>{{stats['nb_assignments']}}</td></tr>
        <tr><td colspan="2">{{ $t('stats.vehicleTimes') }}</td></tr>
      </tbody>
    </table>
    <table class='times' border=1 frame=void rules=rows width="90%">
      <tbody>
        <tr><td class='first'></td>
            <td class='minmax'>{{ $t('stats.min') }}</td>
            <td class='minmax'>{{ $t('stats.avg') }}</td>
            <td class='minmax'>{{ $t('stats.max') }}</td></tr>
        <tr><td class='first'>{{ $t('stats.travel') }}</td>
            <td class='minmax'>{{stats['time_to_dest_stats'][0]}}</td>
            <td class='minmax'>{{stats['time_to_dest_stats'][1]}}</td>
            <td class='minmax'>{{stats['time_to_dest_stats'][2]}}</td>
        </tr>
        <tr><td class='first'>{{ $t('stats.wait') }}</td>
            <td class='minmax'>{{stats['time_margin_stats'][0]}}</td>
            <td class='minmax'>{{stats['time_margin_stats'][1]}}</td>
            <td class='minmax'>{{stats['time_margin_stats'][2]}}</td>
        </tr>
      </tbody>
    </table>
</div>
</template>
<script lang="ts">
import { defineComponent, PropType } from 'vue';
import { StatsData } from './types';

export default defineComponent({
    name: "Stats",
    props: {
        stats: {
            type: Object as PropType<StatsData>,
            required: true
        }
    }
});
</script>

<style scoped>
#stats {
    border: 1px solid black;
    margin: 10px 10px 20px 10px;
    padding: 15px;
}
td {
    font-size: 0.9em;
}
td.value {
    text-align: right;
}
table.main {
    width: 100%;
}
table.times {
    margin-top: 5px;
}
td.first {
    border-right: 1px solid #000;
}
td.minmax {
   text-align: center;
}

h4 {
    margin-bottom: 8px;
    margin-top: 0px;
}
</style>