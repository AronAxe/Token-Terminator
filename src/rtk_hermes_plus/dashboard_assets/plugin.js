// Token Terminator managed Desktop dashboard adapter
import * as sdk from '@hermes/plugin-sdk';
import { jsx, jsxs } from 'react/jsx-runtime';

const { host, useValue, useQuery, Popover, PopoverTrigger, PopoverContent } = sdk;
const fmt = (v) => v == null ? '—' : new Intl.NumberFormat(undefined, {notation:'compact', maximumFractionDigits:1}).format(v);
const full = (v) => v == null ? 'Not available' : new Intl.NumberFormat().format(v);
const usd = (v) => v == null ? 'Not priced' : new Intl.NumberFormat(undefined, {style:'currency',currency:'USD',maximumFractionDigits:4}).format(v);

function owner() {
  return { profile: host.state.profile.get() || 'default', connectionId: host.state.connectionId.get() };
}
function same(a,b) { return a.profile === b.profile && a.connectionId === b.connectionId; }
function line(label, value) {
  return jsxs('div', {style:{display:'flex',justifyContent:'space-between',gap:18,marginTop:10},children:[
    jsx('span',{style:{color:'var(--ui-text-tertiary)'},children:label}),
    jsx('strong',{style:{fontVariantNumeric:'tabular-nums'},children:value})
  ]},label);
}

function Status({ctx}) {
  const profile = useValue(host.state.profile) || 'default';
  const connectionId = useValue(host.state.connectionId);
  const gateway = useValue(host.state.gateway);
  const scope = {profile,connectionId};
  // The actual SDK API is asynchronous (not the abbreviated docs signature).
  // Cache its credential-free routing inventory; never call it during render.
  const routes = useQuery({
    queryKey:['token-terminator','routes',connectionId,profile],
    queryFn:()=>host.profileRoutes(), enabled:gateway === 'open' && !!connectionId,
    staleTime:60000, refetchInterval:60000, refetchIntervalInBackground:false,
    retry:false, gcTime:30000
  });
  const route = routes.data?.find(r => r.connectionId === connectionId && r.profile === profile);
  const backendProfile = route?.targetProfile || profile;
  const query = useQuery({
    queryKey:['token-terminator','summary',connectionId,profile,backendProfile],
    enabled: gateway === 'open' && !!route,
    queryFn: async () => {
      // ctx.rest routes to the ACTIVE connection/profile. It does not take a
      // focused-tile owner: never silently attribute a tile to another backend.
      if (!same(scope,owner())) throw new Error('Profile changed');
      const data = await ctx.rest('/summary',{timeoutMs:5000});
      if (!same(scope,owner()) || data?.scope?.profile !== backendProfile || data.schema_version !== 1)
        throw new Error('Profile changed or incompatible accounting');
      return data;
    },
    staleTime:5000, refetchInterval:10000, refetchIntervalInBackground:false,
    retry:false, gcTime:30000
  });
  const data = query.data;
  const p = data?.profiles?.[0];
  const live = gateway === 'open' && !query.isError && !routes.isError && !!route;
  const count = p?.input.saved;
  const isLocal = route?.mode === 'local' && scope.connectionId === 'local';
  const caption = !live ? 'Offline / last snapshot' : p?.available ? 'Recorded accounting' : 'No accounting yet';
  return jsxs(Popover,{children:[
    jsx(PopoverTrigger,{asChild:true,children:jsx('button',{
      type:'button', title:`Token Terminator · active profile ${profile} · ${caption}`,
      'aria-label':`Token Terminator savings for active profile ${profile}`,
      style:{border:0,background:'transparent',color:'var(--ui-text-secondary)',padding:'0 7px',fontSize:11,cursor:'pointer',fontVariantNumeric:'tabular-nums'},
      children:`TT ↓ ${!live && data ? '~' : ''}${fmt(count)}`
    })}),
    jsxs(PopoverContent,{side:'top',align:'end',sideOffset:8,
      style:{width:320,maxWidth:'90vw',padding:16,fontSize:12,color:'var(--ui-text-primary)'},
      children:[
        jsx('strong',{children:'Token Terminator'}),
        jsx('div',{style:{color:'var(--ui-text-tertiary)',marginTop:5},children:`Active profile: ${profile} · ${caption}`}),
        line('Input saved · measured',full(count)),
        line('Input prepared',full(p?.input.prepared)),
        line('Input used · host reported',full(p?.input.observed)),
        line('Output generated',full(p?.output.observed)),
        line('Output saved','Not measured'),
        line('API-equivalent input saving',usd(p?.value.saved_api_equivalent_usd)),
        line('Output usage · API equivalent',usd(p?.value.output_api_equivalent_usd)),
        line('Billing',p?.billing || 'Unknown'),
        jsx('p',{style:{color:'var(--ui-text-tertiary)',marginTop:12,lineHeight:1.5},children:
          p?.billing === 'subscription' ? 'API-equivalent value is not a subscription discount. Output savings have no measured baseline.' : 'Prepared-request reduction, not an invoice. Rate-card values are gross, exclude overhead and may cover only some models.'}),
        p?.issues?.length ? jsx('p',{role:'status',children:'Some accounting is unavailable. Values cover available records only.'}) : null,
        isLocal ? jsx('button',{type:'button',onClick:()=>{if(same(scope,owner())) ctx.os.openExternal('http://localhost:7474');},
          style:{width:'100%',padding:8,border:'1px solid var(--ui-stroke-secondary)',borderRadius:6,color:'var(--ui-accent)',background:'transparent',cursor:'pointer'},
          children:'Open dashboard · localhost:7474'}) : jsx('p',{children:route?.mode === 'remote' ? 'Remote connection: run the dashboard on that host and use an explicit local port-forward.' : 'Local connection not confirmed. Start token-terminator dashboard on the intended host.'}),
        jsx('div',{style:{fontSize:10,color:'var(--ui-text-tertiary)',marginTop:8},children:data ? `Snapshot ${new Date(data.generated_at).toLocaleTimeString()} · all recorded history` : 'Enable the Python plugin and restart the gateway to load accounting.'})
      ]
    })
  ]});
}

export default {
  id:'token-terminator',name:'Token Terminator',defaultEnabled:false,
  register(ctx) {
    if (!host.state.connectionId || !host.profileRoutes || !Popover || !useQuery)
      throw new Error('Token Terminator requires the current Hermes Desktop plugin SDK');
    ctx.register({id:'savings',area:sdk.STATUSBAR_AREAS.right,order:125,render:()=>jsx(Status,{ctx})});
  }
};
