import React, { useEffect } from 'react';
import { useRouter } from 'expo-router';
import type { SponsoredPlace, RecommendationQuery } from '@photospot/client';
import { api } from '@/api';
import { useAsync } from '@/hooks';
import { Body, Button, Card, Muted } from './ui';
import { PlacePhoto, PhotoCredit } from './place-photo';

function Ad({item}:{item:SponsoredPlace}) {
  const router=useRouter();
  useEffect(()=>{void api.campaignEvent(item.id,'impression').catch(()=>undefined);},[item.id]);
  const open=()=>{void api.campaignEvent(item.id,'click').catch(()=>undefined);router.push({pathname:'/place/[id]',params:{id:item.place_id}});};
  return <Card style={{gap:10}}><Body>광고 · {item.placement==='priority'?'제휴 장소 추천':'파트너 소식'}</Body><Muted size={12}>광고주 {item.sponsor} · 유료 노출이며 정합도 점수에 반영되지 않아요.</Muted>
    <PlacePhoto photo={item.photo} style={{height:item.placement==='banner'?120:180,borderRadius:12}} label={item.place_name}/><PhotoCredit photo={item.photo}/>
    <Body>{item.headline}</Body><Muted>{item.place_name}</Muted><Button title="광고 장소 살펴보기" variant="outline" onPress={open}/></Card>;
}
export function SponsoredPlaces({query,placement,revision}:{query:RecommendationQuery;placement:'banner'|'priority';revision:number}) {
  const data=useAsync(()=>api.sponsorships(query),[query.lat,query.lng,query.radiusM,query.placeGroup,revision]);
  return <>{data.data?.filter(x=>x.placement===placement).map(x=><Ad item={x} key={x.id}/>)}</>;
}
