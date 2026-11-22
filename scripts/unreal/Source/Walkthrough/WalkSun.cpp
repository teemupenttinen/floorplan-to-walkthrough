#include "WalkSun.h"

#include "Walkthrough.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/LightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/PostProcessVolume.h"
#include "EngineUtils.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialParameterCollection.h"

AWalkSun::AWalkSun()
{
	PrimaryActorTick.bCanEverTick = false;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void AWalkSun::BeginPlay()
{
	Super::BeginPlay();
	for (TActorIterator<ADirectionalLight> It(GetWorld()); It; ++It)
	{
		Sun = Cast<UDirectionalLightComponent>(It->GetLightComponent());
		break;
	}
	for (TActorIterator<APostProcessVolume> It(GetWorld()); It; ++It)
	{
		BaseBias = It->Settings.AutoExposureBias;
		break;
	}
	FindLamps();
	SetExposure(DefaultExposure);
	ApplySun();
}

void AWalkSun::SolarPosition(int32 InDay, float InHour, double& El, double& Az) const
{
	// NOAA general solar position equations (accurate to about a degree, plenty for daylight).
	// InHour is local clock time; Tz turns it into solar time.
	const double Tz = UtcOffset + ((bSummerTime && InDay >= SummerStartDay && InDay <= SummerEndDay) ? 1.0 : 0.0);
	const double G = 2.0 * UE_DOUBLE_PI / 365.0 * (InDay - 1 + (InHour - Tz - 12.0) / 24.0);
	const double EqTime = 229.18 * (0.000075 + 0.001868 * FMath::Cos(G) - 0.032077 * FMath::Sin(G)
		- 0.014615 * FMath::Cos(2.0 * G) - 0.040849 * FMath::Sin(2.0 * G));
	const double Decl = 0.006918 - 0.399912 * FMath::Cos(G) + 0.070257 * FMath::Sin(G) - 0.006758 * FMath::Cos(2.0 * G)
		+ 0.000907 * FMath::Sin(2.0 * G) - 0.002697 * FMath::Cos(3.0 * G) + 0.00148 * FMath::Sin(3.0 * G);
	const double Lat = FMath::DegreesToRadians(Latitude);
	const double Ha = FMath::DegreesToRadians((InHour * 60.0 + EqTime + 4.0 * Longitude - 60.0 * Tz) / 4.0 - 180.0);
	El = FMath::Asin(FMath::Sin(Lat) * FMath::Sin(Decl) + FMath::Cos(Lat) * FMath::Cos(Decl) * FMath::Cos(Ha));
	// Azimuth clockwise from north.
	Az = FMath::Atan2(FMath::Sin(Ha), FMath::Cos(Ha) * FMath::Sin(Lat) - FMath::Tan(Decl) * FMath::Cos(Lat)) + UE_DOUBLE_PI;
}

void AWalkSun::ApplySun()
{
	double El, Az;
	SolarPosition(Day, Hour, El, Az);
	SunEl = float(FMath::RadiansToDegrees(El));
	// Azimuth is clockwise from north; model angles are counter-clockwise from +x.
	const double A = FMath::DegreesToRadians(ModelNorthDeg) - Az;
	const FVector ToSunModel(FMath::Cos(A) * FMath::Cos(El), FMath::Sin(A) * FMath::Cos(El), FMath::Sin(El));
	const FVector ToSun(ToSunModel.X, -ToSunModel.Y, ToSunModel.Z);      // model -> Unreal axes
	if (Sun)
	{
		Sun->SetWorldRotation((-ToSun).Rotation());
		// The sky atmosphere needs the sun for the twilight colours, so it stays on until the sky is dark.
		Sun->SetVisibility(SunEl > -18.f);
		Sun->SetIntensity(SunLux);
	}
	// After a large jump (day to night) Lumen needs 10-20 s to settle: shot runs should wait.
}

void AWalkSun::SetHour(float NewHour)
{
	Hour = FMath::Fmod(NewHour + 24.f, 24.f);
	ApplySun();
}

void AWalkSun::SetDay(int32 NewDay)
{
	Day = FMath::Clamp(NewDay, 1, 365);
	ApplySun();
}

void AWalkSun::SetExposure(float Ev)
{
	for (TActorIterator<APostProcessVolume> It(GetWorld()); It; ++It)
	{
		It->Settings.bOverride_AutoExposureBias = true;
		It->Settings.AutoExposureBias = BaseBias + FMath::Clamp(Ev, -4.f, 4.f);
	}
}

void AWalkSun::SetDayWhite(float Kelvin)
{
	for (TActorIterator<APostProcessVolume> It(GetWorld()); It; ++It)
	{
		It->Settings.bOverride_WhiteTemp = true;
		It->Settings.WhiteTemp = Kelvin;
	}
}

void AWalkSun::FindLamps()
{
	Lamps.Reset();
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (!It->ActorHasTag(TEXT("CeilingLight")))
		{
			continue;
		}
		TArray<ULightComponent*> Comps;
		It->GetComponents<ULightComponent>(Comps);
		for (ULightComponent* C : Comps)
		{
			FLamp L;
			L.Light = C;
			L.Intensity = C->Intensity;
			L.Location = C->GetComponentLocation();
			Lamps.Add(L);
		}
	}
	UE_LOG(LogWalk, Log, TEXT("WalkSun: %d lamps"), Lamps.Num());
}

void AWalkSun::ApplyLampGlow(float Level)
{
	// Lamp shades and LED strips glow through MPC LightsOn (M_Flat and M_Textured emissive x LightsOn).
	if (UMaterialParameterCollection* Mpc = LoadObject<UMaterialParameterCollection>(nullptr, *LightsCollection))
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, Mpc, TEXT("LightsOn"), Level);
	}
}

void AWalkSun::SetLamps(bool bOn)
{
	bLampsOn = bOn;
	for (FLamp& L : Lamps)
	{
		if (ULightComponent* C = L.Light.Get())
		{
			C->SetIntensity(L.Intensity);
			C->SetTemperature(LampKelvin);
			C->SetVisibility(bOn);
		}
	}
	ApplyLampGlow(bOn ? 1.f : 0.f);
}

void AWalkSun::SetOnlyRoomAt(const FVector& At, float Level)
{
	// The nearest rect light stands for the room (one soft ceiling light per room in the export).
	int32 Best = INDEX_NONE;
	double BestD = TNumericLimits<double>::Max();
	for (int32 i = 0; i < Lamps.Num(); ++i)
	{
		const double D = FVector::DistSquared(Lamps[i].Location, At);
		if (Lamps[i].Light.IsValid() && D < BestD)
		{
			BestD = D;
			Best = i;
		}
	}
	for (int32 i = 0; i < Lamps.Num(); ++i)
	{
		if (ULightComponent* C = Lamps[i].Light.Get())
		{
			const bool bThis = i == Best && Level > 0.f;
			C->SetIntensity(Lamps[i].Intensity * Level);
			C->SetTemperature(LampKelvin);
			C->SetVisibility(bThis);
		}
	}
	bLampsOn = Best != INDEX_NONE && Level > 0.f;
	ApplyLampGlow(bLampsOn ? Level : 0.f);
}
