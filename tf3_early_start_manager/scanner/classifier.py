"""Stable UI navigation classification for scanned TF3 resources."""
from tf3_early_start_manager.models import Resource

def vehicle_navigation_category(resource: Resource) -> str:
    if resource.domain != 'vehicle': return resource.category
    values=(resource.resource_id,resource.internal_path,str(resource.zip_path),resource.name)
    text=' '.join(v.lower().replace('\\','/') for v in values); parts=[p for p in text.split('/') if p]; base=resource.category
    if resource.carrier=='RAIL' and base=='Air': base='Rail'
    elif resource.carrier=='AIR' and base not in {'Air','AI Traffic'}: base='Air'
    if base=='Air':
        if any(t in text for t in ('graf_zeppelin','zeppelin_nt','zmc2','airship','dirigible')): return 'Air / Airships'
        if any(p in {'plane','aircraft'} for p in parts): return 'Air / Planes'
        if any(p in {'helicopter','heli','aw109'} for p in parts): return 'Air / Helicopters'
        if sum(t in text for t in ('mainrotor','tailrotor','swashplate','collective','cyclic','helicopter','helijah'))>=1 or ('rotor' in text and 'airvehicle' in text): return 'Air / Helicopters'
        if sum(t in text for t in ('aileron','fixed_wing','fixedwing','wing_left','wing_right','turbofan','jet_engine'))>=1: return 'Air / Planes'
        return 'Air / Other'
    if base=='Rail':
        power={'steam':'Steam','diesel':'Diesel','electric':'Electric'}
        if resource.power_type in power: return f'Rail / Trains / {power[resource.power_type]}'
        roles={'passenger':'Passenger','cargo':'Cargo'}
        if resource.vehicle_role in roles: return f'Rail / Wagons / {roles[resource.vehicle_role]}'
        if resource.carrier=='RAIL' and ('tagnpps' in text or any(p in {'waggon','wagon'} for p in parts)):
            fallback={'group':'Technical','support':'Technical'}
            return f"Rail / Wagons / {fallback.get(resource.vehicle_role, 'Other')}"
        if any(p in {'train','rail'} for p in parts): return 'Rail / Trains / Other'
        return 'Rail / Other'
    if base=='Road':
        if 'bus' in parts:return 'Road / Buses'
        if 'truck' in parts:return 'Road / Trucks'
        return 'Road / Other'
    return base
