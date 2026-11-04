"""Deterministic one-minute energy simulation. All energy quantities in Wh, power in W."""
import copy, json
from pathlib import Path
CONFIG=json.loads(Path(__file__).with_name('assumptions.json').read_text())
MODES=('baseline','lunagrid','full')
FAULTS=('solar_damage','eclipse','thermal_route_failure')
class Simulation:
    def __init__(self, mode='full', events=None):
        if mode not in MODES: raise ValueError('Unknown mode')
        self.c=copy.deepcopy(CONFIG); self.mode=mode; self.time=0
        self.events=copy.deepcopy(self.c['events'] if events is None else events)
        self.energy=self.c['battery_capacity_wh']*self.c['initial_soc']/100
        self.storage=self.c['initial_storage_wh']; self.temps={k:self.c[k]['initial_c'] for k in ('habitat','battery')}
        self.faults={}; self.done={'science':0,'rover':0}; self.decisions=[]; self.history=[]; self.last_reasons={}
        self.metrics={'critical_minutes':0,'minimum_soc':self.c['initial_soc'],'electric_heater_wh':0.,'recovered_heat_wh':0.,'rejected_heat_wh':0.,'electrical_heating_avoided_wh':0.,'thermal_safety_violation_minutes':0,'max_electrical_residual_wh':0.,'max_thermal_residual_wh':0.}
        self.live={'solar_w':self.c['solar_w'],'demand_w':0,'requested_w':0,'loads':[],'heat_routes':[],'waste_heat_w':0,'battery_flow_w':0,'curtailed_w':0}
        self.log('Mission','Ready','Identical 12-hour scenario; one-minute energy integration.')
    def log(self,module,action,reason):
        key=module+action
        if self.last_reasons.get(key)==reason:return
        self.last_reasons[key]=reason
        self.decisions.append(dict(time_min=self.time,module=module,action=action,reason=reason))
    def inject(self,kind):
        if kind not in FAULTS:raise ValueError('Unknown fault')
        if self.time>=self.c['mission_minutes']:raise ValueError('Mission complete; reset first')
        self.events.append({'time':self.time,'type':kind,'duration':90})
    def forecast(self):
        return any(self.time<=e['time']<=self.time+self.c['forecast_minutes'] and e['type'] in ('eclipse','solar_damage') for e in self.events)
    def step(self):
        c=self.c; dt=c['step_minutes']/60
        if self.time>=c['mission_minutes']:return self.state()
        for e in self.events:
            if e['time']==self.time:
                self.faults[e['type']]=self.time+e.get('duration',90) if e['type']=='eclipse' else True
                self.log('Scenario',e['type'].replace('_',' ').title(), 'Scenario event applied at mission minute '+str(self.time))
        eclipse=self.faults.get('eclipse',0)>self.time
        solar=0 if eclipse else c['solar_w']*(c['solar_damage_factor'] if self.faults.get('solar_damage') else 1)
        ahead=self.forecast(); soc=self.energy/c['battery_capacity_wh']*100
        active=[]
        for load in c['loads']:
            l=copy.deepcopy(load); status='Active'
            if l['priority']=='Flexible':
                if self.done[l['id']]>=l['duration']:status='Complete'
                elif self.time<l['release']:status='Scheduled'
                elif self.time>=l['deadline']:status='Missed deadline'
                elif self.mode=='baseline' and soc<20:status='Postponed'
                elif self.mode!='baseline' and (eclipse or ahead or soc<c['reserve_soc']+(0 if l['deadline']-self.time<=l['duration']-self.done[l['id']]+60 else 10)):status='Postponed'
                if status=='Postponed':self.log('LunaGrid' if self.mode!='baseline' else 'Baseline','Postpone '+l['name'], 'Forecast shortage: preserve battery reserve.' if ahead else 'Power shortage or low battery reserve; defer flexible work.')
            l['status']=status;l['enabled']=status=='Active';active.append(l)
        waste=sum(l['heat_w'] for l in active if l['enabled'])
        losses={k:c[k]['loss_w']*(c['cold_loss_multiplier'] if eclipse else 1) for k in self.temps}
        needs={k:max(0,losses[k]+(c[k]['target_c']-self.temps[k])*c[k]['capacity_wh_c']/dt) for k in self.temps}
        # Allocate raw source heat once. Recovery losses are accounted separately.
        remaining=min(waste,c['heat_transfer_limit_w']); direct={k:0. for k in self.temps}; routes=[]; transfer_loss=0.
        if self.mode=='full':
            for k in ('battery','habitat'):
                if k=='battery' and self.faults.get('thermal_route_failure'):continue
                raw=min(remaining,needs[k]/c['heat_efficiency']); delivered=raw*c['heat_efficiency']
                direct[k]=delivered;remaining-=raw;transfer_loss+=raw-delivered
                if raw:routes.append(dict(source='Computer / science',target=k.title(),watts=delivered))
        used_raw=sum(direct.values())/c['heat_efficiency']; surplus=waste-used_raw
        storage_before=self.storage; standing_loss=self.storage*c['storage_loss_per_hour']*dt;self.storage-=standing_loss
        discharge={k:0. for k in self.temps}; available=min(c['storage_discharge_limit_w'],self.storage*c['heat_efficiency']/dt)
        if self.mode=='full':
            for k in ('battery','habitat'):
                discharge[k]=min(available,max(0,needs[k]-direct[k]));available-=discharge[k]
            withdrawn=sum(discharge.values())*dt/c['heat_efficiency'];self.storage-=withdrawn
            transfer_loss+=sum(discharge.values())*(1/c['heat_efficiency']-1)
            for k,v in discharge.items():
                if v:routes.append(dict(source='Thermal storage',target=k.title(),watts=v))
        raw_store=0.
        if self.mode=='full' and not sum(discharge.values()):
            raw_store=min(surplus,max(0,c['heat_transfer_limit_w']-used_raw),(c['storage_capacity_wh']-self.storage)/dt/c['heat_efficiency'])
            self.storage+=raw_store*c['heat_efficiency']*dt;transfer_loss+=raw_store*(1-c['heat_efficiency'])
            if raw_store:routes.append(dict(source='Computer / science',target='Thermal storage',watts=raw_store*c['heat_efficiency']))
        rejected=surplus-raw_store
        if rejected:routes.append(dict(source='Equipment',target='Radiator',watts=rejected))
        unmet={k:max(0,needs[k]-direct[k]-discharge[k]) for k in self.temps}
        heater=min(c['heater_limit_w'],sum(unmet.values()))
        active.append(dict(id='heater',name='Electric heater',power_w=heater,heat_w=0,priority='Essential',enabled=heater>0,status='Active' if heater>0 else 'Standby'))
        # Critical first, heater before computer, then flexible. Partial loads are shed.
        requested=sum(l['power_w'] for l in active if l['enabled'])
        budget=solar+min(c['battery_power_limit_w'],self.energy*c['discharge_efficiency']/dt)
        for l in sorted(active,key=lambda l: {'life':0,'comms':1,'heater':2,'computer':3,'science':4,'rover':5}[l['id']]):
            l['delivered_w']=0.
            if l['enabled']:
                supplied=min(l['power_w'],budget) if l['id']=='heater' else (l['power_w'] if budget+1e-9>=l['power_w'] else 0)
                budget-=supplied;l['delivered_w']=supplied
                if supplied<l['power_w']-1e-8:l['status']='Power limited'; l['enabled']=supplied>0
        # If source equipment lost power, redo the step with unavailable heat excluded.
        actual_waste=sum(l['heat_w'] for l in active if l['delivered_w']>0)
        source_shortfall=actual_waste<waste
        if source_shortfall:
            # Conservative rollback: reject all actual heat, undo storage movement,
            # use only already supplied heater electricity. No phantom recovered heat.
            self.storage=storage_before-standing_loss;direct={k:0. for k in self.temps};discharge={k:0. for k in self.temps}
            raw_store=0;transfer_loss=0;rejected=actual_waste;routes=[dict(source='Equipment',target='Radiator',watts=actual_waste)] if actual_waste else []
        waste=actual_waste
        demand=sum(l['delivered_w'] for l in active); heater_actual=active[-1]['delivered_w']
        old_energy=self.energy
        if demand>solar:
            bus_discharge=(demand-solar)*dt;self.energy-=bus_discharge/c['discharge_efficiency'];charge=0;curtail=0; battery_loss=bus_discharge*(1/c['discharge_efficiency']-1)
        else:
            charge=min((solar-demand)*dt,c['battery_power_limit_w']*dt,(c['battery_capacity_wh']-self.energy)/c['charge_efficiency']);self.energy+=charge*c['charge_efficiency'];bus_discharge=0;curtail=(solar-demand)*dt-charge;battery_loss=charge*(1-c['charge_efficiency'])
        self.energy=max(0,min(c['battery_capacity_wh'],self.energy))
        total_unmet=sum(unmet.values()); heater_parts={k:heater_actual*(unmet[k]/total_unmet if total_unmet else 0) for k in self.temps}
        thermal_delta=0
        for k in self.temps:
            d=(direct[k]+discharge[k]+heater_parts[k]-losses[k])*dt
            self.temps[k]+=d/c[k]['capacity_wh_c'];thermal_delta+=d
        thermal_residual=(waste+heater_actual-sum(losses.values())-rejected-transfer_loss)*dt-standing_loss-(self.storage-storage_before)-thermal_delta
        residual=solar*dt-demand*dt-curtail-battery_loss-(self.energy-old_energy)
        m=self.metrics
        m['max_electrical_residual_wh']=max(m['max_electrical_residual_wh'],abs(residual));m['max_thermal_residual_wh']=max(m['max_thermal_residual_wh'],abs(thermal_residual))
        m['critical_minutes']+=int(all(l['delivered_w']==l['power_w'] for l in active if l['priority']=='Critical'))
        m['minimum_soc']=min(m['minimum_soc'],self.energy/c['battery_capacity_wh']*100)
        m['electric_heater_wh']+=heater_actual*dt;m['recovered_heat_wh']+=(sum(direct.values())+raw_store*c['heat_efficiency'])*dt
        m['rejected_heat_wh']+=rejected*dt
        m['electrical_heating_avoided_wh']+=max(0,min(c['heater_limit_w'],sum(needs.values()))-heater)*dt if not source_shortfall else 0
        m['thermal_safety_violation_minutes']+=int(any(not c[k]['safe_min_c']<=self.temps[k]<=c[k]['safe_max_c'] for k in self.temps))
        for l in active:
            if l['id'] in self.done and l['delivered_w']==l['power_w'] and l['status']=='Active':self.done[l['id']]+=1
            if l['id'] in self.done:l['progress']=self.done[l['id']]/l['duration']*100
        if self.mode=='full':
            path=', '.join(r['target'] for r in routes if r['target']!='Radiator') or 'radiator only'
            self.log('HEATBANK','Heat routing',path+('; computer → battery route unavailable' if self.faults.get('thermal_route_failure') else ''))
            self.log('Coordinator','Heater request', 'Recovered and stored heat reduce remaining electric demand.' if sum(direct.values())+sum(discharge.values()) else 'Electric heating covers remaining thermal demand.')
        self.time+=1
        self.live=dict(solar_w=solar,demand_w=demand,requested_w=requested,loads=active,heat_routes=routes,waste_heat_w=waste,battery_flow_w=(self.energy-old_energy)/dt,curtailed_w=curtail/dt)
        self.history.append(dict(time_min=self.time,solar_kw=solar/1000,demand_kw=demand/1000,soc=self.energy/c['battery_capacity_wh']*100,habitat=self.temps['habitat'],battery=self.temps['battery'],heater_kwh=m['electric_heater_wh']/1000,recovered_kwh=m['recovered_heat_wh']/1000))
        return self.state()
    def kpis(self):
        return dict(self.metrics,critical_availability=100*self.metrics['critical_minutes']/max(1,self.time),flexible_tasks_completed=sum(self.done[l['id']]>=l['duration'] for l in self.c['loads'] if l['id'] in self.done),task_minutes_completed=sum(self.done.values()))
    def state(self):
        upcoming=sorted((e for e in self.events if e['time']>=self.time),key=lambda e:e['time'])
        return dict(time_min=self.time,mode=self.mode,complete=self.time>=self.c['mission_minutes'],battery_soc=self.energy/self.c['battery_capacity_wh']*100,thermal_storage_wh=self.storage,thermal_storage_capacity_wh=self.c['storage_capacity_wh'],habitat_temp_c=self.temps['habitat'],battery_temp_c=self.temps['battery'],faults={**self.faults,'eclipse':self.faults.get('eclipse',0)>self.time},upcoming=upcoming[0] if upcoming else None,decisions=self.decisions[-35:],metrics=self.kpis(),**self.live)
def compare(events=None):
    result={}
    for mode in MODES:
        s=Simulation(mode,events)
        for _ in range(s.c['mission_minutes']):s.step()
        result[mode]={'metrics':s.kpis(),'history':s.history}
    return result
if __name__=='__main__':
    print(json.dumps({k:v['metrics'] for k,v in compare().items()},indent=2))
