#include "WalkDoor.h"

#include "Components/StaticMeshComponent.h"

AWalkDoor::AWalkDoor()
{
	PrimaryActorTick.bCanEverTick = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent->SetMobility(EComponentMobility::Movable);
	Hinge = CreateDefaultSubobject<USceneComponent>(TEXT("Hinge"));
	Hinge->SetupAttachment(RootComponent);
	Hinge->SetMobility(EComponentMobility::Movable);
	Leaf = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Leaf"));
	Leaf->SetupAttachment(Hinge);
	Leaf->SetMobility(EComponentMobility::Movable);
	Leaf->SetCollisionProfileName(TEXT("BlockAll"));
	Glass = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Glass"));
	Glass->SetupAttachment(Hinge);
	Glass->SetMobility(EComponentMobility::Movable);
	Glass->SetCollisionEnabled(ECollisionEnabled::QueryOnly);     // the E key can still aim at it
	Glass->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
}

void AWalkDoor::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	Snap();
}

void AWalkDoor::Snap()
{
	Hinge->SetRelativeRotation(FRotator(0.f, TargetYaw(), 0.f));
}

void AWalkDoor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Current = Hinge->GetRelativeRotation().Yaw;
	const float Delta = FMath::FindDeltaAngleDegrees(Current, TargetYaw());
	if (FMath::Abs(Delta) < 0.01f)
	{
		return;
	}
	const float Step = FMath::Clamp(Delta, -Speed * DeltaSeconds, Speed * DeltaSeconds);
	// Sweep off: a door that stops on the player's capsule would stay half open.
	Hinge->SetRelativeRotation(FRotator(0.f, Current + Step, 0.f));
}
